import asyncio
from abc import ABC, abstractmethod
import time
import logging
from collections import namedtuple
import uuid
from roboflo import Worker as Worker_roboflo

# from frgpascal.maestro import Maestro
from frgpascal.hardware.liquidhandler import expected_timings

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

task_tuple = namedtuple("task", ["function", "estimated_duration", "other_workers"])


class WorkerTemplate(Worker_roboflo):
    """Template class for Workers
    This class contains the nuts and bolts to schedule and execute tasks
    for each "worker". Workers are considered single units of one or more
    hardware components that act in unison to complete tasks.
    """

    def __init__(self, name, capacity, maestro=None, planning=False, initial_fill=0):
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

        super().__init__(name=name, capacity=capacity, initial_fill=initial_fill)

    def prime(self, loop):
        asyncio.set_event_loop(loop)
        self.loop = loop
        self.queue = asyncio.PriorityQueue()

    def start(self):
        def future_callback(future):
            try:
                future.result()
            except Exception as e:
                self.logger.exception(f"Exception in {self}")
                # if future.exception(): #your long thing had an exception
                #     self.logger.error(f'Exception in {self}: {future.exception()}')

        self.working = True
        for _ in range(self.capacity):
            future = asyncio.run_coroutine_threadsafe(self.worker(), self.loop)
            future.add_done_callback(future_callback)

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
            while True:
                if len(self.queue.queue) > 0:
                    time_until_next = self.queue.queue[0][0] - self.maestro.time
                    if time_until_next <= 5:  # within 5 seconds of start time
                        break
                await asyncio.sleep(0.2)

            _, task = await self.queue.get()  # blocking wait for next task
            task_description = f'{task["name"]}, {task["sample"]}'
            sample = self.maestro.samples[task["sample"]]
            sample_task = sample["tasks"][task["id"]]
            # print(f"starting {task_description}")
            if task is None:  # finished flag
                break
            # wait for all previous tasks to complete

            with self.maestro.lock_pendingtasks:
                self.maestro.pending_tasks.append(task["id"])

            if task["precedent"] is not None:
                first = True
                found = False
                while not found:
                    with self.maestro.lock_completedtasks:
                        found = task["precedent"] in self.maestro.completed_tasks
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
            wait_for = task["start"] - (self.maestro.time)
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

            sample_task["start_actual"] = self.maestro.time
            function = self.functions[task["name"]].function
            details = sample_task.get("details", {})
            if asyncio.iscoroutinefunction(function):
                self.logger.info(f"executing {task_description} as coroutine")
                output_dict = await function(sample, details)
            else:
                self.logger.info(f"executing {task_description} as thread")
                future = asyncio.gather(
                    self.loop.run_in_executor(
                        self.maestro.threadpool,
                        function,
                        sample,
                        details,
                    )
                )
                future.add_done_callback(future_callback)
                output_dict = await future
                output_dict = output_dict[0]
            if output_dict is None:
                output_dict = {}
            # update task lists
            output_dict["finish_actual"] = self.maestro.time
            sample_task.update(output_dict)

            self.logger.info(f"finished {task_description}")
            with self.maestro.lock_completedtasks:
                self.maestro.completed_tasks[task["id"]] = self.maestro.time
            with self.maestro.lock_pendingtasks:
                self.maestro.pending_tasks.remove(task["id"])
            self.queue.task_done()

    def __hash__(self):
        return hash(str(type(self)))


class Worker_GantryGripper(WorkerTemplate):
    def __init__(self, maestro=None, planning=False):
        super().__init__(
            name="GantryGripper", maestro=maestro, planning=planning, capacity=1
        )
        self.functions = {
            # "moveto": self.gantry.moveto,
            # "moverel": self.gantry.moverel,
            # "open": self.gripper.open,
            # "close": self.gripper.close,
            # "transfer": self.maestro.transfer,
            "idle_gantry": task_tuple(
                function=self.idle_gantry, estimated_duration=6, other_workers=[]
            ),
            "spincoater_to_hotplate": task_tuple(
                function=self.spincoater_to_hotplate,
                estimated_duration=27,
                other_workers=[Worker_SpincoaterLiquidHandler],
            ),
            "spincoater_to_storage": task_tuple(
                function=self.spincoater_to_storage,
                estimated_duration=30,
                other_workers=[Worker_SpincoaterLiquidHandler],
            ),
            "spincoater_to_characterization": task_tuple(
                function=self.spincoater_to_characterization,
                estimated_duration=30,
                other_workers=[Worker_SpincoaterLiquidHandler, Worker_Characterization],
            ),
            "hotplate_to_spincoater": task_tuple(
                function=self.hotplate_to_spincoater,
                estimated_duration=33,
                other_workers=[Worker_SpincoaterLiquidHandler],
            ),
            "hotplate_to_storage": task_tuple(
                function=self.hotplate_to_storage,
                estimated_duration=18,
                other_workers=[],
            ),
            "hotplate_to_characterization": task_tuple(
                function=self.hotplate_to_characterization,
                estimated_duration=18,
                other_workers=[Worker_Characterization],
            ),
            "storage_to_spincoater": task_tuple(
                function=self.storage_to_spincoater,
                estimated_duration=33,
                other_workers=[Worker_SpincoaterLiquidHandler],
            ),
            "storage_to_hotplate": task_tuple(
                function=self.storage_to_hotplate,
                estimated_duration=18,
                other_workers=[],
            ),
            "storage_to_characterization": task_tuple(
                function=self.storage_to_characterization,
                estimated_duration=15,
                other_workers=[Worker_Characterization],
            ),
            "characterization_to_spincoater": task_tuple(
                function=self.characterization_to_spincoater,
                estimated_duration=33,
                other_workers=[Worker_Characterization, Worker_SpincoaterLiquidHandler],
            ),
            "characterization_to_hotplate": task_tuple(
                function=self.characterization_to_hotplate,
                estimated_duration=18,
                other_workers=[Worker_Characterization],
            ),
            "characterization_to_storage": task_tuple(
                function=self.characterization_to_storage,
                estimated_duration=18,
                other_workers=[Worker_Characterization],
            ),
        }

    def idle_gantry(self, sample, details):
        self.maestro.idle_gantry()

    def spincoater_to_hotplate(self, sample, details):
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
        sample["hotplate_slot"] = {
            "hotplate": hotplate_name,
            "slot": slot,
        }

    def spincoater_to_storage(self, sample, details):
        p1 = self.spincoater()
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p2 = self.storage[tray](slot)

        self.maestro.transfer(p1, p2)

    def spincoater_to_characterization(self, sample, details):
        p1 = self.spincoater()
        p2 = self.characterization.axis()

        self.transfer(p1, p2)

    def hotplate_to_storage(self, sample, details):
        hotplate, hpslot = (
            sample["hotplate_slot"]["hotplate"],
            sample["hotplate_slot"]["slot"],
        )
        p1 = self.hotplates[hotplate](hpslot)

        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p2 = self.storage[tray](slot)

        self.maestro.transfer(p1, p2)
        self.hotplates[hotplate].unload(slot=hpslot)

    def hotplate_to_characterization(self, sample, details):
        hotplate, hpslot = (
            sample["hotplate_slot"]["hotplate"],
            sample["hotplate_slot"]["slot"],
        )
        p1 = self.hotplates[hotplate](hpslot)
        p2 = self.characterization.axis()

        self.maestro.transfer(p1, p2)
        self.hotplates[hotplate].unload(slot=hpslot)

    def hotplate_to_spincoater(self, sample, details):
        hotplate, hpslot = (
            sample["hotplate_slot"]["hotplate"],
            sample["hotplate_slot"]["slot"],
        )
        p1 = self.hotplates[hotplate](hpslot)
        p2 = self.spincoater()

        self.maestro.transfer(p1, p2)
        self.hotplates[hotplate].unload(slot=hpslot)

    def storage_to_spincoater(self, sample, details):
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p1 = self.maestro.storage[tray](slot)
        p2 = self.maestro.spincoater()

        self.maestro.transfer(p1, p2)

    def storage_to_hotplate(self, sample, details):
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
        sample["hotplate_slot"] = {
            "hotplate": hotplate_name,
            "slot": slot,
        }

    def storage_to_characterization(self, sample, details):
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p1 = self.storage[tray](slot)
        p2 = self.characterization.axis()

        self.maestro.transfer(p1, p2)

    def characterization_to_spincoater(self, sample, details):
        p1 = self.characterization.axis()
        p2 = self.spincoater()

        self.maestro.transfer(p1, p2)

    def characterization_to_hotplate(self, sample, details):
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
        sample["hotplate_slot"] = {
            "hotplate": hotplate_name,
            "slot": slot,
        }

    def characterization_to_storage(self, sample, details):
        p1 = self.characterization.axis()
        tray, slot = (
            sample["storage_slot"]["tray"],
            sample["storage_slot"]["slot"],
        )
        p2 = self.storage[tray](slot)

        self.maestro.transfer(p1, p2)


class Worker_Hotplate(WorkerTemplate):
    def __init__(self, capacity, maestro=None, planning=False):
        super().__init__(
            name="Hotplate", maestro=maestro, planning=planning, capacity=capacity
        )
        self.functions = {
            "anneal": task_tuple(
                function=self.anneal, estimated_duration=None, other_workers=[]
            ),
        }

    async def anneal(self, sample, details):
        await asyncio.sleep(details["duration"])


class Worker_Storage(WorkerTemplate):
    def __init__(self, capacity, maestro=None, planning=False, initial_fill=0):
        super().__init__(
            name="Storage",
            maestro=maestro,
            planning=planning,
            capacity=capacity,
            initial_fill=initial_fill,
        )
        self.functions = {
            "rest": task_tuple(
                function=self.rest, estimated_duration=180, other_workers=[]
            ),
        }

    async def rest(self, sample, details):
        await asyncio.sleep(details["duration"])


class Worker_SpincoaterLiquidHandler(WorkerTemplate):
    def __init__(self, maestro=None, planning=False):
        super().__init__(
            name="SpincoaterLiquidHandler",
            maestro=maestro,
            planning=planning,
            capacity=1,
        )
        self.functions = {
            "spincoat": task_tuple(
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
                    print(
                        f"\t\t{t0-self.maestro.nist_time():.2f} droptime found {taskid}"
                    )
                await asyncio.sleep(0.1)
        print(f"\t{t0-self.maestro.nist_time():.2f} found all droptimes")
        return completed_tasks

    async def _set_spinspeeds(self, steps, t0, headstart):
        await asyncio.sleep(headstart)
        tnext = headstart
        for step in steps:
            self.spincoater.set_rpm(rpm=step["rpm"], acceleration=step["acceleration"])
            tnext += step["duration"]
            while self.maestro.nist_time() - t0 < tnext:
                await asyncio.sleep(0.1)
            print(f"\t\t{t0-self.maestro.nist_time():.2f} finished step")
        self.spincoater.stop()
        print(f"\t{t0-self.maestro.nist_time():.2f} finished all spinspeed steps")

    def _expected_aspiration_duration(self, drop) -> float:
        """Estimate the duration (seconds) liquid aspiration will require for a given drop

        Args:
            drop (dict): dictionary of drop parameters

        Returns:
            float: duration, in seconds
        """
        ac = self.liquidhandler.CONSTANTS["aspirate"]  # aspiration constants
        d = (
            ac["preparetip"]
            + drop["volume"] / 100
            + self.liquidhandler.CONSTANTS["travel"]
        )
        d += drop["pre_mix"][0] * (
            ac["premix"]["a"] * drop["pre_mix"][1] + ac["premix"]["b"]
        )  # overhead time for aspirate+dispense cycles to mix solution prior to final aspiration
        if drop["touch_tip"]:
            d += ac["touchtip"]
        if drop["slow_retract"]:
            d += ac["slowretract"]
        if drop["air_gap"]:
            d += ac["airgap"]

        return d

    def _expected_staging_duration(self, drop) -> float:
        if drop["slow_travel"]:
            return self.liquidhandler.CONSTANTS["travel_slow"]
        else:
            return self.liquidhandler.CONSTANTS["travel"]

    def _expected_dispense_duration(self, drop) -> float:
        if drop["slow_travel"]:
            return self.liquidhandler.CONSTANTS["dispensedelay_slow"]
        else:
            return self.liquidhandler.CONSTANTS["dispensedelay"]

    def _generatelhtasks_onedrop(self, t0, drop):
        liquidhandlertasks = {}

        (
            aspirate_duration,
            staging_duration,
            dispense_duration,
        ) = expected_timings(drop)

        headstart = (
            aspirate_duration + staging_duration + dispense_duration - drop["time"]
        )
        headstart = max(headstart, 0)  # stick to t=0 start time if it works out

        aspirate_time = (
            t0
            + drop["time"]
            + headstart
            - aspirate_duration
            - staging_duration
            - dispense_duration
        )
        liquidhandlertasks[
            "aspirate_solution"
        ] = self.liquidhandler.aspirate_for_spincoating(
            nist_time=aspirate_time,
            tray=drop["solution"]["well"]["labware"],
            well=drop["solution"]["well"]["well"],
            volume=drop["volume"],
            pipette="perovskite",
            slow_retract=drop["slow_retract"],
            air_gap=drop["air_gap"],
            touch_tip=drop["touch_tip"],
            pre_mix=drop["pre_mix"],
            reuse_tip=drop["reuse_tip"],
        )
        liquidhandlertasks["stage_solution"] = self.liquidhandler.stage_perovskite(
            nist_time=aspirate_time + 1  # immediately after aspirate
        )

        last_time = t0 + drop["time"] + headstart - dispense_duration
        liquidhandlertasks["dispense_solution"] = self.liquidhandler.drop_perovskite(
            nist_time=last_time, rate=drop["rate"], height=drop["height"]
        )

        self.liquidhandler.cleanup(nist_time=last_time + 0.5)

        return headstart, liquidhandlertasks

    def _generatelhtasks_twodrops(self, t0, drop0, drop1):

        aspirate0_duration, staging0_duration, dispense0_duration = expected_timings(
            drop0
        )
        aspirate1_duration, staging1_duration, dispense1_duration = expected_timings(
            drop1
        )
        if (drop1["time"] - drop0["time"]) < (
            aspirate1_duration + staging1_duration + dispense1_duration
        ):  # if the two drops are too close in time, let's aspirate them both at the beginning
            return self._generatelhtasks_twodrops_together(
                t0,
                drop0,
                drop1,
                aspirate0_duration,
                staging0_duration,
                dispense0_duration,
                aspirate1_duration,
                staging1_duration,
                dispense1_duration,
            )

        else:
            return self._generatelhtasks_twodrops_separate(
                t0,
                drop0,
                drop1,
                aspirate0_duration,
                staging0_duration,
                dispense0_duration,
                aspirate1_duration,
                staging1_duration,
                dispense1_duration,
            )
        #     headstart = max(
        #         2
        #         * (
        #             self.liquidhandler.ASPIRATION_DELAY
        #             + self.liquidhandler.DISPENSE_DELAY
        #         )
        #         - drop0["time"],
        #         0,
        #     )

        #     aspirate_time = (
        #         0 + drop0["time"] + headstart - self.liquidhandler.ASPIRATION_DELAY
        #     )
        #     liquidhandlertasks[
        #         "aspirate_solution0"
        #     ] = self.liquidhandler.aspirate_for_spincoating(
        #         nist_time=aspirate_time,
        #         tray=drop0["solution"]["well"]["labware"],
        #         well=drop0["solution"]["well"]["well"],
        #         volume=drop0["volume"],
        #         pipette="perovskite",
        #         slow_retract=drop0["slow_retract"],
        #         air_gap=drop0["air_gap"],
        #         touch_tip=drop0["touch_tip"],
        #         pre_mix=drop0["pre_mix"],
        #     )
        #     liquidhandlertasks[
        #         "aspirate_solution1"
        #     ] = self.liquidhandler.aspirate_for_spincoating(
        #         nist_time=aspirate_time + 0.1,  # immediately after first aspirate
        #         tray=drop1["solution"]["well"]["labware"],
        #         well=drop1["solution"]["well"]["well"],
        #         volume=drop1["volume"],
        #         pipette="antisolvent",
        #         slow_retract=drop1["slow_retract"],
        #         air_gap=drop1["air_gap"],
        #         touch_tip=drop1["touch_tip"],
        #         pre_mix=drop1["pre_mix"],
        #     )
        #     liquidhandlertasks["stage_solution0"] = self.liquidhandler.stage_perovskite(
        #         nist_time=aspirate_time + 0.2  # immediately after second aspirate
        #     )

        #     dispense0_time = (
        #         t0 + drop0["time"] + headstart - self.liquidhandler.DISPENSE_DELAY
        #     )
        #     liquidhandlertasks[
        #         "dispense_solution0"
        #     ] = self.liquidhandler.drop_perovskite(
        #         nist_time=dispense0_time, height=drop0["height"], rate=drop0["rate"]
        #     )

        #     liquidhandlertasks[
        #         "stage_solution1"
        #     ] = self.liquidhandler.stage_antisolvent(nist_time=dispense0_time + 0.1)
        # else:  # we have enough dead time to come back to aspirate the second drop
        #     headstart = max(
        #         self.liquidhandler.ASPIRATION_DELAY
        #         + self.liquidhandler.DISPENSE_DELAY
        #         - drop0["time"],
        #         0,
        #     )
        #     aspirate0_time = (
        #         t0 + drop0["time"] + headstart - self.liquidhandler.ASPIRATION_DELAY,
        #     )
        #     liquidhandlertasks[
        #         "aspirate_solution0"
        #     ] = self.liquidhandler.aspirate_for_spincoating(
        #         nist_time=aspirate0_time,
        #         tray=drop0["solution"]["well"]["labware"],
        #         well=drop0["solution"]["well"]["well"],
        #         volume=drop0["volume"],
        #         pipette="perovskite",
        #         slow_retract=drop0["slow_retract"],
        #         air_gap=drop0["air_gap"],
        #         touch_tip=drop0["touch_tip"],
        #         pre_mix=drop0["pre_mix"],
        #     )
        #     liquidhandlertasks["stage_solution0"] = self.liquidhandler.stage_perovskite(
        #         nist_time=aspirate0_time + 0.1  # immediately after second aspirate
        #     )

        #     dispense0_time = (
        #         t0 + drop0["time"] + headstart - self.liquidhandler.DISPENSE_DELAY
        #     )
        #     aspirate1_time = (
        #         t0 + drop1["time"] + headstart - self.liquidhandler.ASPIRATION_DELAY
        #     )

        #     liquidhandlertasks[
        #         "dispense_solution0"
        #     ] = self.liquidhandler.drop_perovskite(
        #         nist_time=dispense0_time, height=drop0["height"], rate=drop0["rate"]
        #     )

        #     if aspirate1_time - dispense0_time > (
        #         self.liquidhandler.DISPENSE_DELAY * 5
        #     ):  # move pipette to idle off of the chuck
        #         liquidhandlertasks[
        #             "clear_chuck_between_drops"
        #         ] = self.liquidhandler.stage_perovskite(nist_time=dispense0_time + 0.3)

        #     liquidhandlertasks[
        #         "aspirate_solution1"
        #     ] = self.liquidhandler.aspirate_for_spincoating(
        #         nist_time=aspirate1_time,
        #         tray=drop1["solution"]["well"]["labware"],
        #         well=drop1["solution"]["well"]["well"],
        #         volume=drop1["volume"],
        #         pipette="antisolvent",
        #         slow_retract=drop1["slow_retract"],
        #         air_gap=drop1["air_gap"],
        #         touch_tip=drop1["touch_tip"],
        #         pre_mix=drop1["pre_mix"],
        #     )
        # # Dispenses

        # dispense1_time = (
        #     t0 + drop1["time"] + headstart - self.liquidhandler.DISPENSE_DELAY
        # )
        # liquidhandlertasks["dispense_solution1"] = self.liquidhandler.drop_antisolvent(
        #     nist_time=dispense1_time, height=drop1["height"], rate=drop1["rate"]
        # )

        # self.liquidhandler.cleanup(nist_time=dispense1_time + 0.5)

        # return headstart, liquidhandlertasks

    def _generatelhtasks_twodrops_together(
        self,
        t0,
        drop0,
        drop1,
        aspirate0_duration,
        staging0_duration,
        dispense0_duration,
        aspirate1_duration,
        staging1_duration,
        dispense1_duration,
    ):
        """Aspirate both solutions together, not enough time to do them one by one"""
        liquidhandlertasks = {}

        # timings
        if drop0["slow_travel"] or drop1["slow_travel"]:
            # both pipettes hold liquid at once, so if one is slow travel, both must be slow travel.
            # If one is slow, recalculate times with slow travel
            drop0["slow_travel"] = True
            drop1["slow_travel"] = True

            (
                aspirate0_duration,
                staging0_duration,
                dispense0_duration,
            ) = expected_timings(drop0)
            (
                aspirate1_duration,
                staging1_duration,
                dispense1_duration,
            ) = expected_timings(drop1)

        headstart = (
            aspirate0_duration
            + aspirate1_duration
            + staging0_duration
            + dispense0_duration
            - drop0["time"]
        )
        headstart = max(headstart, 0)
        aspirate_time = (
            t0
            + drop0["time"]
            + headstart
            - aspirate0_duration
            - aspirate1_duration
            - staging0_duration
            - dispense0_duration
        )
        dispense0_time = t0 + drop0["time"] + headstart - dispense0_duration
        dispense1_time = t0 + drop1["time"] + headstart - dispense1_duration

        # build tasklist
        liquidhandlertasks[
            "aspirate_solution0"
        ] = self.liquidhandler.aspirate_for_spincoating(
            nist_time=aspirate_time,
            tray=drop0["solution"]["well"]["labware"],
            well=drop0["solution"]["well"]["well"],
            volume=drop0["volume"],
            pipette="perovskite",
            slow_retract=drop0["slow_retract"],
            air_gap=drop0["air_gap"],
            touch_tip=drop0["touch_tip"],
            pre_mix=drop0["pre_mix"],
            reuse_tip=drop0["reuse_tip"],
        )
        liquidhandlertasks[
            "aspirate_solution1"
        ] = self.liquidhandler.aspirate_for_spincoating(
            nist_time=aspirate_time + 0.1,
            tray=drop1["solution"]["well"]["labware"],
            well=drop1["solution"]["well"]["well"],
            volume=drop1["volume"],
            pipette="antisolvent",
            slow_retract=drop1["slow_retract"],
            air_gap=drop1["air_gap"],
            touch_tip=drop1["touch_tip"],
            pre_mix=drop1["pre_mix"],
            reuse_tip=drop1["reuse_tip"],
        )
        liquidhandlertasks["stage_solution0"] = self.liquidhandler.stage_perovskite(
            nist_time=aspirate_time + 0.2,  # immediately after aspiration
            slow_travel=drop0["slow_travel"],
        )
        liquidhandlertasks["dispense_solution0"] = self.liquidhandler.drop_perovskite(
            nist_time=dispense0_time,
            height=drop0["height"],
            rate=drop0["rate"],
            slow_travel=drop0["slow_travel"],
        )

        liquidhandlertasks["stage_solution1"] = self.liquidhandler.stage_antisolvent(
            nist_time=dispense0_time + 0.1,  # immediately after first dispense
            slow_travel=drop1["slow_travel"],
        )

        liquidhandlertasks["dispense_solution1"] = self.liquidhandler.drop_antisolvent(
            nist_time=dispense1_time,
            height=drop1["height"],
            rate=drop1["rate"],
            slow_travel=drop1["slow_travel"],
        )

        self.liquidhandler.cleanup(nist_time=dispense1_time + 0.1)

        return headstart, liquidhandlertasks

    def _generatelhtasks_twodrops_separate(
        self,
        t0,
        drop0,
        drop1,
        aspirate0_duration,
        staging0_duration,
        dispense0_duration,
        aspirate1_duration,
        staging1_duration,
        dispense1_duration,
    ):
        """Aspirate, stage, and dispense first drop before aspirating the second drop."""
        liquidhandlertasks = {}

        # timings
        headstart = (
            aspirate0_duration + staging0_duration + dispense0_duration - drop0["time"]
        )
        headstart = max(headstart, 0)
        aspirate0_time = (
            t0
            + drop0["time"]
            + headstart
            - aspirate0_duration
            - staging0_duration
            - dispense0_duration
        )
        dispense0_time = t0 + drop0["time"] + headstart - dispense0_duration
        aspirate1_time = (
            t0
            + drop1["time"]
            + headstart
            - aspirate1_duration
            - staging1_duration
            - dispense1_duration
        )
        dispense1_time = t0 + drop1["time"] + headstart - dispense1_duration

        # build tasklist
        liquidhandlertasks[
            "aspirate_solution0"
        ] = self.liquidhandler.aspirate_for_spincoating(
            nist_time=aspirate0_time,
            tray=drop0["solution"]["well"]["labware"],
            well=drop0["solution"]["well"]["well"],
            volume=drop0["volume"],
            pipette="perovskite",
            slow_retract=drop0["slow_retract"],
            air_gap=drop0["air_gap"],
            touch_tip=drop0["touch_tip"],
            pre_mix=drop0["pre_mix"],
            reuse_tip=drop0["reuse_tip"],
        )
        liquidhandlertasks["stage_solution0"] = self.liquidhandler.stage_perovskite(
            nist_time=aspirate0_time + 0.1,  # immediately after aspiration
            slow_travel=drop0["slow_travel"],
        )
        liquidhandlertasks["dispense_solution0"] = self.liquidhandler.drop_perovskite(
            nist_time=dispense0_time,
            height=drop0["height"],
            rate=drop0["rate"],
            slow_travel=drop0["slow_travel"],
        )

        if aspirate1_time - dispense0_time > 2:  # move pipette to idle off of the chuck
            liquidhandlertasks[
                "clear_chuck_between_drops"
            ] = self.liquidhandler.stage_perovskite(nist_time=dispense0_time + 0.1)

        liquidhandlertasks[
            "aspirate_solution1"
        ] = self.liquidhandler.aspirate_for_spincoating(
            nist_time=aspirate1_time,
            tray=drop1["solution"]["well"]["labware"],
            well=drop1["solution"]["well"]["well"],
            volume=drop1["volume"],
            pipette="antisolvent",
            slow_retract=drop1["slow_retract"],
            air_gap=drop1["air_gap"],
            touch_tip=drop1["touch_tip"],
            pre_mix=drop1["pre_mix"],
            reuse_tip=drop1["reuse_tip"],
        )
        liquidhandlertasks["stage_solution1"] = self.liquidhandler.stage_antisolvent(
            nist_time=aspirate1_time + 0.1,  # immediately after aspiration
            slow_travel=drop1["slow_travel"],
        )

        liquidhandlertasks["dispense_solution1"] = self.liquidhandler.drop_antisolvent(
            nist_time=dispense1_time,
            height=drop1["height"],
            rate=drop1["rate"],
            slow_travel=drop1["slow_travel"],
        )

        self.liquidhandler.cleanup(nist_time=dispense1_time + 0.5)

        return headstart, liquidhandlertasks

    def spincoat(self, sample, details):
        """executes a series of spin coating steps. A final "stop" step is inserted
        at the end to bring the rotor to a halt.

        Args:
            recipe (SpincoatRecipe): recipe of spincoating steps + drop times

        Returns:
            record: dictionary of recorded spincoating process.
        """
        self.liquidhandler.server._start_directly()  # connect to liquid handler websocket

        t0 = self.maestro.nist_time()
        self.spincoater.start_logging()
        ### set up liquid handler tasks
        if len(details["drops"]) == 1:
            headstart, liquidhandlertasks = self._generatelhtasks_onedrop(
                t0=t0, drop=details["drops"][0]
            )
        else:  # assume two drops, planning does not allow for >2
            headstart, liquidhandlertasks = self._generatelhtasks_twodrops(
                t0=t0, drop0=details["drops"][0], drop1=details["drops"][1]
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tasks_future = asyncio.gather(
            self._monitor_droptimes(liquidhandlertasks, t0),
            self._set_spinspeeds(details["steps"], t0, headstart),
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
        print(f"{t0-self.maestro.nist_time():.2f} finished all tasks")
        rpm_log = self.spincoater.finish_logging()
        print(f"{t0-self.maestro.nist_time():.2f} finished logging")
        self.liquidhandler.server.stop()  # disconnect from liquid handler websocket
        print(f"{t0-self.maestro.nist_time():.2f} server stopped")
        return {
            "liquidhandler_timings": {**drop_times},
            "spincoater_log": {**rpm_log},
            "headstart": headstart,
        }


class Worker_Characterization(WorkerTemplate):
    def __init__(self, maestro=None, planning=False):
        super().__init__(
            name="Characterization", maestro=maestro, planning=planning, capacity=1
        )
        self.functions = {
            "characterize": task_tuple(
                function=self.characterize, estimated_duration=160, other_workers=[]
            ),
        }

    def characterize(self, sample, details):
        self.characterization.run(samplename=sample["name"])
