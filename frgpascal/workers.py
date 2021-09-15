import asyncio
from abc import ABC, abstractmethod
import time
import logging
from collections import namedtuple
import uuid

# from frgpascal.maestro import Maestro

# from frgpascal.hardware.gantry import Gantry
# from frgpascal.hardware.gripper import Gripper
# from frgpascal.hardware.spincoater import SpinCoater
# from frgpascal.hardware.liquidhandler import OT2
# from frgpascal.hardware.hotplate import HotPlate
# from frgpascal.hardware.sampletray import SampleTray
# from frgpascal.hardware.characterizationline import (
#     CharacterizationAxis,
#     CharacterizationLine,
# )

task = namedtuple("task", ["function", "estimated_duration", "other_workers"])


class WorkerTemplate(ABC):
    """Template class for Workers
    This class contains the nuts and bolts to schedule and execute tasks
    for each "worker". Workers are considered single units of one or more
    hardware components that act in unison to complete tasks.
    """

    def __init__(self, n_workers, maestro=None, planning=False):
        if not planning:
            self.logger = logging.getLogger("PASCAL")
            self.maestro = maestro
            self.gantry = maestro.gantry
            self.gripper = maestro.gripper
            self.spincoater = maestro.spincoater
            self.characterization = maestro.characterization
            self.liquidhandler = maestro.liquidhandler
            self.hotplates = maestro.hotplates
            self.storage = maestro.storage

            self.working = False
            self.POLLINGRATE = 0.1  # seconds
        self.n_workers = n_workers

    def prime(self, loop):
        asyncio.set_event_loop(loop)
        self.loop = loop
        self.queue = asyncio.PriorityQueue()

    def start(self):
        self.working = True
        for _ in range(self.n_workers):
            asyncio.run_coroutine_threadsafe(self.worker(), self.loop)

    def stop_workers(self):
        self.working = False
        # self.thread.join()

    def add_task(self, task):
        # if not self.working:
        #     raise RuntimeError("Cannot add to queue, workers not running!")
        payload = (task["start"], task)
        self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)

    async def worker(self):
        """process items from the queue + keep the maestro lists updated"""

        def future_callback(future):
            try:
                future.result()
            except Exception as e:
                self.logger.exception(f"Exception in {self}")
                # if future.exception(): #your long thing had an exception
                #     self.logger.error(f'Exception in {self}: {future.exception()}')

        while self.working:
            _, task = await self.queue.get()  # blocking wait for next task
            task_description = f'{task["task"]}, {task["sample"]}'
            sample = self.maestro.samples[task["sample"]]
            sample_task = [t for t in sample["tasks"] if t["task"] == task["task"]][0]
            # print(f"starting {task_description}")
            if task is None:  # finished flag
                break

            # wait for all previous tasks to complete

            with self.maestro.lock_pendingtasks:
                self.maestro.pending_tasks.append(task["id"])
            for precedent in task["precedents"]:
                found = False
                first = True
                while not found:
                    with self.maestro.lock_completedtasks:
                        found = precedent in self.maestro.completed_tasks
                    if found:
                        break
                    else:
                        if first:
                            self.logger.info(
                                f"waiting for precedents of {task_description}"
                            )
                        await asyncio.sleep(self.POLLINGRATE)
                        first = False

            # wait for this task's target start time
            wait_for = task["start"] - (self.maestro.nist_time() - self.maestro.t0)
            if wait_for > 0:
                self.logger.info(
                    f"waiting {wait_for} seconds for {task_description} start time"
                )
                await asyncio.sleep(wait_for)

            # execute this task
            # function = partial(
            #     self.functions[task["function"]],
            #     args=task["args"],
            #     kwargs=task["kwargs"],
            # )

            sample_task["start_actual"] = self.maestro.nist_time() - self.maestro.t0
            function = self.functions[task["task"]]
            if asyncio.iscoroutinefunction(function):
                self.logger.info(f"executing {task_description} as coroutine")
                await function(sample)
            else:
                self.logger.info(f"executing {task_description} as thread")
                future = asyncio.gather(
                    self.loop.run_in_executor(self.maestro.threadpool, function, sample)
                )
                future.add_done_callback(future_callback)
                await future
                # try:
                #     future.result()
                # except:
                #     self.logger.info(
                #         f"{task_description} failed: {future.exception()}"
                #     )

            # update task lists
            sample_task["finish_actual"] = self.maestro.nist_time() - self.maestro.t0
            self.logger.info(f"finished {task_description}")
            with self.maestro.lock_completedtasks:
                self.maestro.completed_tasks[task["id"]] = (
                    self.maestro.nist_time() - self.maestro.t0
                )
            with self.maestro.lock_pendingtasks:
                self.maestro.pending_tasks.remove(task["id"])
            self.queue.task_done()

    def __hash__(self):
        return hash(str(type(self)))

    def __eq__(self, other):
        return type(self) == type(other)


class Worker_GantryGripper(WorkerTemplate):
    def __init__(self, maestro=None, planning=False):
        super().__init__(maestro=maestro, planning=planning, n_workers=1)
        self.functions = {
            # "moveto": self.gantry.moveto,
            # "moverel": self.gantry.moverel,
            # "open": self.gripper.open,
            # "close": self.gripper.close,
            # "transfer": self.maestro.transfer,
            "idle_gantry": task(
                function=self.idle_gantry, estimated_duration=20, other_workers=[]
            ),
            "spincoater_to_hotplate": task(
                function=self.spincoater_to_hotplate,
                estimated_duration=25,
                other_workers=[Worker_SpincoaterLiquidHandler],
            ),
            "spincoater_to_storage": task(
                function=self.spincoater_to_storage,
                estimated_duration=25,
                other_workers=[Worker_SpincoaterLiquidHandler],
            ),
            "spincoater_to_characterization": task(
                function=self.spincoater_to_characterization,
                estimated_duration=25,
                other_workers=[Worker_SpincoaterLiquidHandler, Worker_Characterization],
            ),
            "hotplate_to_spincoater": task(
                function=self.hotplate_to_spincoater,
                estimated_duration=33,
                other_workers=[Worker_SpincoaterLiquidHandler],
            ),
            "hotplate_to_storage": task(
                function=self.hotplate_to_storage,
                estimated_duration=18,
                other_workers=[],
            ),
            "hotplate_to_characterization": task(
                function=self.hotplate_to_characterization,
                estimated_duration=18,
                other_workers=[Worker_Characterization],
            ),
            "storage_to_spincoater": task(
                function=self.storage_to_spincoater,
                estimated_duration=33,
                other_workers=[Worker_SpincoaterLiquidHandler],
            ),
            "storage_to_hotplate": task(
                function=self.storage_to_hotplate,
                estimated_duration=18,
                other_workers=[],
            ),
            "storage_to_characterization": task(
                function=self.storage_to_characterization,
                estimated_duration=18,
                other_workers=[Worker_Characterization],
            ),
            "characterization_to_spincoater": task(
                function=self.characterization_to_spincoater,
                estimated_duration=33,
                other_workers=[Worker_Characterization, Worker_SpincoaterLiquidHandler],
            ),
            "characterization_to_hotplate": task(
                function=self.characterization_to_hotplate,
                estimated_duration=18,
                other_workers=[Worker_Characterization],
            ),
            "characterization_to_storage": task(
                function=self.characterization_to_storage,
                estimated_duration=18,
                other_workers=[Worker_Characterization],
            ),
        }

    def idle_gantry(self, sample):
        self.maestro.idle_gantry()

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
        p2 = self.hotplates[hotplate_name](slot)
        self.maestro.transfer(p1, p2)

        self.hotplates[hotplate_name].load(slot, sample)
        sample["anneal_recipe"]["location"] = {
            "hotplate": hotplate_name,
            "slot": slot,
        }

    def spincoater_to_storage(self, sample):
        p1 = self.spincoater()
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p2 = self.storage[tray](slot)

        self.maestro.transfer(p1, p2)

    def spincoater_to_characterization(self, sample):
        p1 = self.spincoater()
        p2 = self.characterization.axis()

        self.transfer(p1, p2)

    def hotplate_to_storage(self, sample):
        hotplate, hpslot = (
            sample["anneal_recipe"]["location"]["hotplate"],
            sample["anneal_recipe"]["location"]["slot"],
        )
        p1 = self.hotplates[hotplate](hpslot)

        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p2 = self.storage[tray](slot)

        self.maestro.transfer(p1, p2)
        self.hotplates[hotplate].unload(slot=hpslot)

    def hotplate_to_characterization(self, sample):
        hotplate, hpslot = (
            sample["anneal_recipe"]["location"]["hotplate"],
            sample["anneal_recipe"]["location"]["slot"],
        )
        p1 = self.hotplates[hotplate](hpslot)
        p2 = self.characterization.axis()

        self.maestro.transfer(p1, p2)
        self.hotplates[hotplate].unload(slot=hpslot)

    def hotplate_to_spincoater(self, sample):
        hotplate, hpslot = (
            sample["anneal_recipe"]["location"]["hotplate"],
            sample["anneal_recipe"]["location"]["slot"],
        )
        p1 = self.hotplates[hotplate](hpslot)
        p2 = self.spincoater()

        self.maestro.transfer(p1, p2)
        self.hotplates[hotplate].unload(slot=hpslot)

    def storage_to_spincoater(self, sample):
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p1 = self.maestro.storage[tray](slot)
        p2 = self.maestro.spincoater()

        self.maestro.transfer(p1, p2)

    def storage_to_hotplate(self, sample):
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p1 = self.maestro.storage[tray](slot)
        for hotplate_name, hp in self.hotplates.items():
            try:
                slot = hp.get_open_slot()
                break
            except:
                slot = None
        if slot is None:
            raise ValueError("No slots available on any hotplate!")
        p2 = self.hotplates[hotplate_name](slot)

        self.maestro.transfer(p1, p2)
        self.hotplates[hotplate_name].load(slot, sample)

    def storage_to_characterization(self, sample):
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p1 = self.storage[tray](slot)
        p2 = self.characterization.axis()

        self.maestro.transfer(p1, p2)

    def characterization_to_spincoater(self, sample):
        p1 = self.characterization.axis()
        p2 = self.spincoater()

        self.maestro.transfer(p1, p2)

    def characterization_to_hotplate(self, sample):
        p1 = self.characterization.axis()
        for hotplate_name, hp in self.hotplates.items():
            try:
                slot = hp.get_open_slot()
                break
            except:
                slot = None
        if slot is None:
            raise ValueError("No slots available on any hotplate!")
        p2 = self.hotplates[hotplate_name](slot)

        self.maestro.transfer(p1, p2)
        self.hotplates[hotplate_name].load(slot, sample)

    def characterization_to_storage(self, sample):
        p1 = self.characterization.axis()
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p2 = self.storage[tray](slot)

        self.maestro.transfer(p1, p2)


class Worker_Hotplate(WorkerTemplate):
    def __init__(self, n_workers, maestro=None, planning=False):
        super().__init__(maestro=maestro, planning=planning, n_workers=n_workers)
        self.functions = {
            "anneal": task(
                function=self.anneal, estimated_duration=None, other_workers=[]
            ),
        }

    async def anneal(self, sample):
        await asyncio.sleep(sample["anneal_recipe"]["duration"])


class Worker_Storage(WorkerTemplate):
    def __init__(self, n_workers, maestro=None, planning=False):
        super().__init__(maestro=maestro, planning=planning, n_workers=n_workers)
        self.functions = {
            "rest": task(function=self.rest, estimated_duration=180, other_workers=[]),
        }

    async def rest(self, sample):
        await asyncio.sleep(180)


class Worker_SpincoaterLiquidHandler(WorkerTemplate):
    def __init__(self, maestro=None, planning=False):
        super().__init__(maestro=maestro, planning=planning, n_workers=1)
        self.functions = {
            "spincoat": task(
                function=self.spincoat, estimated_duration=None, other_workers=[]
            ),
        }

    async def _monitor_droptimes(self, liquidhandlertasks, t0):
        completed_tasks = {}
        while len(liquidhandlertasks) > len(completed_tasks):
            for task, taskid in liquidhandlertasks.items():
                if task in completed_tasks:
                    continue  # already got this one, skip
                if taskid in self.liquidhandler.server.completed_tasks:
                    completed_tasks[task] = (
                        self.liquidhandler.server.completed_tasks[taskid] - t0
                    )  # save the completion time of the liquidhandler task
                await asyncio.sleep(0.1)
        return completed_tasks

    async def _set_spinspeeds(self, steps, t0, headstart):
        await asyncio.sleep(headstart)
        tnext = headstart
        for step in steps:
            self.spincoater.set_rpm(rpm=step["rpm"], acceleration=step["acceleration"])
            tnext += step["duration"]
            while self.maestro.nist_time() - t0 <= tnext:
                await asyncio.sleep(0.1)
        self.spincoater.stop()

    def spincoat(self, sample):
        """executes a series of spin coating steps. A final "stop" step is inserted
        at the end to bring the rotor to a halt.

        Args:
            recipe (SpincoatRecipe): recipe of spincoating steps + drop times

        Returns:
            record: dictionary of recorded spincoating process.
        """
        self.liquidhandler.server._start_directly()  # connect to liquid handler websocket

        recipe = sample["spincoat_recipe"]
        t0 = self.maestro.nist_time()
        self.spincoater.start_logging()
        ### set up liquid handler tasks
        liquidhandlertasks = {}
        ## Aspirations
        # if drop times are close, pipette up both solutions at the beginning
        if (
            recipe["antisolvent"]["droptime"] - recipe["solution"]["droptime"]
            > (self.liquidhandler.ASPIRATION_DELAY + self.liquidhandler.DISPENSE_DELAY)
            * 2
        ):
            headstart = max(
                2
                * (
                    self.liquidhandler.ASPIRATION_DELAY
                    + self.liquidhandler.DISPENSE_DELAY
                )
                - recipe["solution"]["droptime"],
                0,
            )
            liquidhandlertasks[
                "aspirate_both"
            ] = self.liquidhandler.aspirate_both_for_spincoating(
                nist_time=t0
                + recipe["solution"]["droptime"]
                + headstart
                - self.liquidhandler.ASPIRATION_DELAY,
                psk_tray=recipe["solution"]["solution"]["well"]["tray"],
                psk_well=recipe["solution"]["solution"]["well"]["slot"],
                psk_volume=recipe["solution"]["volume"],
                antisolvent_tray=recipe["antisolvent"]["solution"]["well"]["tray"],
                antisolvent_well=recipe["antisolvent"]["solution"]["well"]["slot"],
                antisolvent_volume=recipe["antisolvent"]["volume"],
            )
            liquidhandlertasks[
                "dispense_solution"
            ] = self.liquidhandler.drop_perovskite(
                nist_time=t0
                + recipe["solution"]["droptime"]
                + headstart
                - self.liquidhandler.DISPENSE_DELAY
            )
            liquidhandlertasks[
                "stage_antisolvent"
            ] = self.liquidhandler.stage_antisolvent(
                nist_time=t0
                + recipe["antisolvent"]["droptime"]
                + headstart
                - self.liquidhandler.STAGING_DELAY,
            )
        else:
            headstart = max(
                self.liquidhandler.ASPIRATION_DELAY
                + self.liquidhandler.DISPENSE_DELAY
                - recipe["solution"]["droptime"],
                0,
            )
            liquidhandlertasks[
                "aspirate_solution"
            ] = self.liquidhandler.aspirate_for_spincoating(
                nist_time=t0
                + recipe["solution"]["droptime"]
                + headstart
                - self.liquidhandler.ASPIRATION_DELAY,
                tray=recipe["solution"]["solution"]["well"]["tray"],
                well=recipe["solution"]["solution"]["well"]["slot"],
                volume=recipe["solution"]["volume"],
                pipette="perovskite",
            )
            liquidhandlertasks[
                "dispense_solution"
            ] = self.liquidhandler.drop_perovskite(
                nist_time=t0
                + recipe["solution"]["droptime"]
                + headstart
                - self.liquidhandler.DISPENSE_DELAY
            )

            liquidhandlertasks[
                "aspirate_antisolvent"
            ] = self.liquidhandler.aspirate_for_spincoating(
                nist_time=t0
                + recipe["antisolvent"]["droptime"]
                + headstart
                - self.liquidhandler.ASPIRATION_DELAY,
                tray=recipe["antisolvent"]["solution"]["well"]["tray"],
                well=recipe["antisolvent"]["solution"]["well"]["slot"],
                volume=recipe["antisolvent"]["volume"],
                pipette="antisolvent",
            )
        # Dispenses

        liquidhandlertasks[
            "dispense_antisolvent"
        ] = self.liquidhandler.drop_antisolvent(
            nist_time=t0
            + recipe["antisolvent"]["droptime"]
            + headstart
            - self.liquidhandler.DISPENSE_DELAY
        )
        liquidhandlertasks["clear_chuck"] = self.liquidhandler.drop_antisolvent(
            nist_time=t0 + recipe["antisolvent"]["droptime"] + headstart - 0.5
        )  # final task to be done

        self.liquidhandler.cleanup(
            nist_time=t0 + recipe["antisolvent"]["droptime"] + headstart
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tasks_future = asyncio.gather(
            self._monitor_droptimes(liquidhandlertasks, t0),
            self._set_spinspeeds(recipe["steps"], t0, headstart),
        )

        def future_callback(future):
            try:
                future.result()
            except Exception as e:
                self.logger.exception(f"Exception in {self}")
                # if future.exception(): #your long thing had an exception
                #     self.logger.error(f'Exception in {self}: {future.exception()}')

        tasks_future.add_done_callback(future_callback)

        drop_times, _ = loop.run_until_complete(tasks_future)
        rpm_log = self.spincoater.finish_logging()
        self.liquidhandler.server.stop()  # disconnect from liquid handler websocket

        self.maestro.samples[sample["name"]]["spincoat_recipe"]["record"] = {
            **drop_times,
            **rpm_log,
            "headstart": headstart,
        }


class Worker_Characterization(WorkerTemplate):
    def __init__(self, maestro=None, planning=False):
        super().__init__(maestro=maestro, planning=planning, n_workers=1)
        self.functions = {
            "characterize": task(
                function=self.characterize, estimated_duration=95, other_workers=[]
            ),
        }

    def characterize(self, sample):
        self.characterization.run(samplename=sample["name"])
