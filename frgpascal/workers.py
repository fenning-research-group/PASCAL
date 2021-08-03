from threading import Thread, Lock
import asyncio
from queue import Queue
from abc import ABC, abstractmethod
import time
from functools import partial

# from frgpascal.maestro import Maestro
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper
from frgpascal.hardware.spincoater import SpinCoater
from frgpascal.hardware.liquidhandler import OT2
from frgpascal.hardware.hotplate import HotPlate
from frgpascal.hardware.sampletray import SampleTray
from frgpascal.hardware.characterizationline import (
    CharacterizationAxis,
    CharacterizationLine,
)


class WorkerTemplate(ABC):
    def __init__(self, maestro, n_workers=1):
        self.maestro = maestro
        self.gantry = maestro.gantry
        self.gripper = maestro.gripper
        self.spincoater = maestro.spincoater
        self.characterization = maestro.characterization
        self.liquidhandler = maestro.liquidhandler
        self.hotplates = maestro.hotplates
        self.storage = maestro.storage

        self.loop = asyncio.get_event_loop()
        self.queue = asyncio.Queue()
        self.working = False
        self.POLLINGRATE = 0.1

    def main(self, workers):
        self.working = True
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(asyncio.wait(workers))

    def start(self):
        self.thread = Thread(
            target=self.main, args=[self.worker() for _ in range(self.n_workers)]
        )
        self.thread.start()

    def stop_workers(self):
        self.working = False
        self.thread.join()

    def add_to_queue(self, payload):
        if not self.workers_running:
            raise RuntimeError("Cannot add to queue, workers not running!")
        self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)

    async def worker(self):
        """process items from the queue + keep the maestro lists updated"""
        while self.working:
            task = await self.queue.get()  # blocking wait for next task
            if task is None:  # finished flag
                break

            # wait for all previous tasks to complete
            with self.maestro.lock_pendingtasks:
                self.maestro.pending_tasks.append(task["taskid"])
            for precedent in task["preceding_tasks"]:
                with self.maestro.lock_completedtasks:
                    found = precedent in self.maestro.completed_tasks
                if found:
                    continue
                else:
                    await asyncio.sleep(self.POLLINGRATE)

            # wait for this task's target start time
            wait_for = (
                self.maestro.nist_time() - task["time"] - self.maestro.t0
            )  # how long to wait before executing
            if wait_for > 0:
                await asyncio.sleep(wait_for)

            # execute this task
            function = partial(
                self.functions[task["function"]],
                args=task["args"],
                kwargs=task["kwargs"],
            )
            if asyncio.iscoroutinefunction(function):
                await function()
            else:
                await self.loop.run_in_executor(None, function)

            # update task lists
            with self.maestro.lock_completedtasks:
                self.maestro.completed_tasks["taskid"] = (
                    self.maestro.nist_time() - self.maestro.t0
                )
            with self.maestro.lock_pendingtasks:
                self.maestro.pending_tasks.remove(task["taskid"])
            await self.queue.task_done()


class Worker_GantryGripper(WorkerTemplate):
    def __init__(self, maestro):
        super().__init__(maestro=maestro)
        self.functions = {
            "moveto": self.gantry.moveto,
            "moverel": self.gantry.moverel,
            "open": self.gripper.open,
            "close": self.gripper.close,
            "transfer": self.maestro.transfer,
            "idle_gantry": self.maestro.idle_gantry,
            "storage_to_spincoater": self.storage_to_spincoater,
            "spincoater_to_hotplate": self.spincoater_to_hotplate,
            "hotplate_to_storage": self.hotplate_to_storage,
            "storage_to_characterization": self.storage_to_characterization,
            "characterization_to_storage": self.characterization_to_storage,
        }

    def catch(self):
        """
        Close gripper barely enough to pick up sample, not all the way to avoid gripper finger x float
        """
        caught_successfully = False
        while not caught_successfully and self.maestro.CATCHATTEMPTS > 0:
            self.gripper.close(slow=True)
            self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
            self.gripper.open(self.SAMPLEWIDTH - 2)
            self.gripper.open(self.SAMPLEWIDTH - 1)
            time.sleep(0.1)
            if (
                not self.gripper.is_under_load()
            ):  # if springs not pulling on grippers, assume that the sample is grabbed
                caught_successfully = True
                break
            else:
                self.CATCHATTEMPTS -= 1
                # lets jog the gripper position and try again.
                self.gripper.close()
                self.gripper.open(self.SAMPLEWIDTH + self.SAMPLETOLERANCE, slow=False)
                # self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
                self.gantry.moverel(z=-self.gantry.ZHOP_HEIGHT)

        if not caught_successfully:
            self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
            self.gripper.close()
            raise ValueError("Failed to pick up sample!")

    def release(self):
        """
        Open gripper slowly release sample without jogging position
        """
        self.gripper.open(
            self.maestro.SAMPLEWIDTH + self.maestro.SAMPLETOLERANCE, slow=True
        )  # slow to prevent sample position shifting upon release

    def idle_gantry(self):
        """Move gantry to the idle position. This is primarily to provide cameras a clear view"""
        self.gantry.moveto(self.maestro.IDLECOORDINATES)
        self.gripper.close()

    def transfer(self, p1, p2, zhop=True):
        self.release()  # open the grippers
        self.gantry.moveto(p1, zhop=zhop)  # move to the pickup position
        self.catch()  # pick up the sample. this function checks to see if gripper picks successfully
        self.gantry.moveto(
            x=p2[0], y=p2[1], z=p2[2] + 5, zhop=zhop
        )  # move just above destination
        if self.gripper.is_under_load():
            raise ValueError("Sample dropped in transit!")
        self.gantry.moveto(p2, zhop=False)  # if not dropped, move to the final position
        self.release()  # drop the sample
        self.gantry.moverel(
            z=self.gantry.ZHOP_HEIGHT
        )  # move up a bit, mostly to avoid resting gripper on hotplate
        self.gripper.close()  # fully close gripper to reduce servo strain

    def storage_to_spincoater(self, sample):
        tray, slot = (
            sample["storage"]["storage_location"]["tray"],
            sample["storage"]["storage_location"]["slot"],
        )
        p1 = self.maestro.storage[tray](slot)
        p2 = self.maestro.spincoater()

        self.maestro.release()  # open the grippers
        self.gantry.moveto(p1, zhop=True)  # move to the pickup position
        self.catch()  # pick up the sample. this function checks to see if gripper picks successfully
        self.gantry.moveto(
            x=p2[0], y=p2[1], z=p2[2] + 5, zhop=True
        )  # move just above destination
        if self.gripper.is_under_load():
            raise ValueError("Sample dropped in transit!")
        self.spincoater.vacuum_on()
        self.gantry.moveto(p2, zhop=False)  # if not dropped, move to the final position
        self.release()  # drop the sample
        self.gantry.moverel(
            z=self.gantry.ZHOP_HEIGHT
        )  # move up a bit, mostly to avoid resting gripper on hotplate
        self.gripper.close()  # fully close gripper to reduce servo strain

    def spincoater_to_hotplate(self, sample):
        p1 = self.spincoater()
        for hotplate_name, hp in self.hotplates.items():
            try:
                slot = hp.get_open_slot()
                break
            except:
                slot = None
        if slot is None:
            raise ValueError("No slots available on any hotplate!")
        self.hotplates[hotplate_name].load(slot, sample)
        p2 = self.hotplates[hotplate_name](slot)

        self.release()  # open the grippers
        self.gantry.moveto(p1, zhop=True)  # move to the pickup position
        self.catch()  # pick up the sample. this function checks to see if gripper picks successfully
        self.spincoater.vacuum_off()
        self.gantry.moveto(
            x=p2[0], y=p2[1], z=p2[2] + 5, zhop=True
        )  # move just above destination
        if self.gripper.is_under_load():
            raise ValueError("Sample dropped in transit!")
        self.gantry.moveto(p2, zhop=False)  # if not dropped, move to the final position
        self.release()  # drop the sample
        self.gantry.moverel(
            z=self.gantry.ZHOP_HEIGHT
        )  # move up a bit, mostly to avoid resting gripper on hotplate
        self.gripper.close()  # fully close gripper to reduce servo strain

        self.sample["anneal_recipe"]["location"] = {
            "hotplate": hotplate_name,
            "slot": slot,
        }

    def hotplate_to_storage(self, sample):
        hotplate, slot = (
            self.sample["anneal_recipe"]["location"]["hotplate"],
            self.sample["anneal_recipe"]["location"]["slot"],
        )
        p1 = self.hotplates[hotplate](slot)

        tray, slot = (
            sample["storage"]["storage_location"]["tray"],
            sample["storage"]["storage_location"]["slot"],
        )
        p2 = self.storage[tray](slot)

        self.transfer(p1, p2)
        self.hotplates[hotplate].unload(sample)

    def storage_to_characterization(self, sample):
        tray, slot = (
            sample["storage"]["storage_location"]["tray"],
            sample["storage"]["storage_location"]["slot"],
        )
        p1 = self.storage[tray](slot)
        p2 = self.characterization.axis()

        self.transfer(p1, p2)

    def characterization_to_storage(self, sample):
        p1 = self.characterization.axis()
        tray, slot = (
            sample["storage"]["storage_location"]["tray"],
            sample["storage"]["storage_location"]["slot"],
        )
        p2 = self.storage[tray](slot)

        self.transfer(p1, p2)


class Worker_Hotplate(WorkerTemplate):
    def __init__(self, maestro, n_workers):
        super().__init__(maestro=maestro)
        self.functions = {
            "anneal": self.anneal,
        }

    async def anneal(self, sample):
        await asyncio.sleep(sample["anneal_recipe"]["duration"])


class Worker_Storage(WorkerTemplate):
    def __init__(self, maestro, n_workers):
        super().__init__(maestro=maestro)
        self.functions = {
            "cooldown": self.cooldown,
        }

    async def anneal(self, sample):
        await asyncio.sleep(180)


class Worker_SpincoaterLiquidHandler(WorkerTemplate):
    def __init__(self, maestro):
        super().__init__(maestro=maestro)
        self.functions = {
            "vacuum_on": self.spincoater.vacuum_on,
            "vacuum_off": self.spincoater.vacuum_off,
            "set_rpm": self.spincoater.set_rpm,
            "stop": self.spincoater.stop,
            "start_logging": self.spincoater.start_logging,
            "finish_logging": self.spincoater.finish_logging,
            "aspirate_for_spincoating": self.liquidhandler.aspirate_for_spincoating,
            "aspirate_both_for_spincoating": self.liquidhandler.aspirate_both_for_spincoating,
            "stage_perovskite": self.liquidhandler.stage_perovskite,
            "stage_antisolvent": self.liquidhandler.stage_antisolvent,
            "drop_perovskite": self.liquidhandler.drop_perovskite,
            "drop_antisolvent": self.liquidhandler.drop_antisolvent,
            "clear_chuck": self.liquidhandler.clear_chuck,
            "cleanup": self.liquidhandler.cleanup,
            "spincoat": self.spincoat,
        }

    def spincoat(self, sample):
        """executes a series of spin coating steps. A final "stop" step is inserted
        at the end to bring the rotor to a halt.

        Args:
            recipe (SpincoatRecipe): recipe of spincoating steps + drop times

        Returns:
            record: dictionary of recorded spincoating process.
        """
        recipe = sample["spincoat_recipe"]
        solution_dropped = False
        antisolvent_dropped = False
        record = {}

        self.spincoater.start_logging()
        spincoating_in_progress = True
        t0 = self.nist_time()
        tnext = 0
        for start_time, (rpm, acceleration, duration) in zip(
            recipe.start_times, recipe.steps
        ):
            tnext += start_time
            tnow = self.nist_time() - t0  # time relative to recipe start
            while (
                tnow <= tnext
            ):  # loop and check for drop times until next spin step is reached
                if not solution_dropped and tnow >= recipe.solution_droptime:
                    self.liquidhandler.drop_perovskite()
                    solution_dropped = True
                    record["solution_drop"] = tnow
                if not antisolvent_dropped and tnow >= recipe.antisolvent_droptime:
                    self.liquidhandler.drop_antisolvent()
                    antisolvent_dropped = True
                    record["antisolvent_drop"] = tnow
                time.sleep(0.1)

            self.spincoater.set_rpm(rpm=rpm, acceleration=acceleration)

        self.spincoater.stop()
        record.update(self.spincoater.finish_logging())

        sample["spincoat_recipe"]["record"] = record


class Worker_Characterization(WorkerTemplate):
    def __init__(self, maestro):
        super().__init__(maestro=maestro)
        self.functions = {
            "moveto": self.characterization.axis.moveto,
            "moverel": self.characterization.axis.moverel,
            "movetotransfer": self.characterization.axis.movetotransfer,
            "characterize": self.characterization.run,
        }


# class Worker_Hotplate:
#     def __init__(self, maestro: Maestro, hotplate: HotPlate, n_workers: int):
#         self.nist_time = self.maestro.nist_time
#         self.queue = Queue()
#         self.functions = {
#             "anneal": self.anneal_timer
#         }  # this must be filled in by each method to map tasks to functions

#     def start(self):
#         self.thread = Thread(target=self.worker)
#         self.thread.start()

#     def worker(self):
#         """process items from the queue + keep the maestro lists updated"""
#         while True:
#             task = self.queue.get()  # blocking wait for next task
#             if task is None:
#                 break  # None signals all tasks complete

#             # wait for all previous tasks to complete
#             with self.maestro.lock_pendingtasks:
#                 self.maestro.pending_tasks.append(task["taskid"])
#             for precedent in task["preceding_tasks"]:
#                 with self.maestrto.lock_completedtasks:
#                     found = precedent in self.maestro.completed_tasks
#                 if found:
#                     continue
#                 else:
#                     time.sleep(0.25)

#             # wait for this task's target start time
#             wait_for = (
#                 self.maestro.nist_time() - task["nist_time"]
#             )  # how long to wait before executing
#             if wait_for > 0:
#                 time.sleep(wait_for)

#             # execute this task
#             function = self.functions[task["function"]]
#             function(*task["args"], **task["kwargs"])

#             # update task lists
#             with self.lock_completedtasks:
#                 self.completed_tasks["taskid"] = self.nist_time()
#             with self.lock_pendingtasks:
#                 self.pending_tasks.remove(task["taskid"])
