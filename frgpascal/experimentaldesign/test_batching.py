import json
import asyncio
from abc import ABC, abstractmethod
from threading import Lock, Thread
import time
from functools import partial
import numpy as np
from concurrent.futures import ThreadPoolExecutor

speedup_factor = 50


def load_netlist(filename):
    with open(filename) as f:
        netlist = json.load(f)
    tasks = netlist["tasks"]
    samples = netlist["samples"]
    return samples, tasks


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

        self.working = False
        self.POLLINGRATE = 0.0001  # seconds
        self.n_workers = n_workers

    # def main(self, workers):
    #     self.working = True
    #     asyncio.set_event_loop(self.loop)
    #     if not self.loop.is_running():
    #         self.loop.run_until_complete(asyncio.wait(workers))
    # else:
    #     self.loop.call_soon_threadsafe(asyncio.wait(workers))

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
                            print(f"waiting for precedents of {task_description}")
                        await asyncio.sleep(self.POLLINGRATE)
                        first = False

            # wait for this task's target start time
            wait_for = task["start"] - (self.maestro.nist_time() - self.maestro.t0)
            if wait_for > 0:
                print(f"\twaiting {wait_for} seconds for {task_description} start time")
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
                print(f"\t\texecuting {task_description} as coro")
                await function(task)
            else:
                print(f"\t\texecuting {task_description} as thread")
                await self.loop.run_in_executor(
                    self.maestro.threadpool, partial(function, task)
                )

            # update task lists
            sample_task["finish_actual"] = self.maestro.nist_time() - self.maestro.t0
            print(f"\t\t\tfinished {task_description}")
            with self.maestro.lock_completedtasks:
                self.maestro.completed_tasks[task["id"]] = (
                    self.maestro.nist_time() - self.maestro.t0
                )
            with self.maestro.lock_pendingtasks:
                self.maestro.pending_tasks.remove(task["id"])
            self.queue.task_done()


class Worker_GantryGripper(WorkerTemplate):
    def __init__(self, maestro):
        super().__init__(maestro=maestro, n_workers=1)
        self.functions = {
            "moveto": partial(self.pause, 12 / speedup_factor),
            "moverel": partial(self.pause, 12 / speedup_factor),
            "open": partial(self.pause, 1 / speedup_factor),
            "close": partial(self.pause, 1 / speedup_factor),
            "transfer": partial(self.pause, 30 / speedup_factor),
            "idle_gantry": partial(self.pause, 30 / speedup_factor),
            "storage_to_spincoater": partial(self.pause, 30 / speedup_factor),
            "spincoater_to_hotplate": partial(self.pause, 30 / speedup_factor),
            "hotplate_to_storage": partial(self.pause, 30 / speedup_factor),
            "storage_to_characterization": partial(self.pause, 30 / speedup_factor),
            "characterization_to_storage": partial(self.pause, 30 / speedup_factor),
        }

    def pause(self, t, task):
        # t -= np.random.random() * 5 / speedup_factor
        time.sleep(min(t, 0))


class Worker_Hotplate(WorkerTemplate):
    def __init__(self, maestro, n_workers):
        super().__init__(maestro=maestro, n_workers=n_workers)
        self.functions = {
            "anneal": self.anneal,
        }

    async def anneal(self, task):
        sample = self.maestro.samples[task["sample"]]
        await asyncio.sleep(sample["anneal_recipe"]["duration"] / speedup_factor)

    # def anneal(self, task):
    #     sample = self.maestro.samples[task["sample"]]
    #     time.sleep(sample["anneal_recipe"]["duration"] / speedup_factor)


class Worker_Storage(WorkerTemplate):
    def __init__(self, maestro, n_workers):
        super().__init__(maestro=maestro, n_workers=n_workers)
        self.functions = {
            "cooldown": self.cooldown,
        }

    async def cooldown(self, task):
        sample = self.maestro.samples[task["sample"]]
        await asyncio.sleep(180 / speedup_factor)

    # def cooldown(self, task):
    #     sample = self.maestro.samples[task["sample"]]
    #     time.sleep(180 / speedup_factor)


class Worker_SpincoaterLiquidHandler(WorkerTemplate):
    def __init__(self, maestro):
        super().__init__(maestro=maestro, n_workers=1)
        self.functions = {
            "spincoat": self.spincoat,
        }

    async def spincoat(self, task):
        """executes a series of spin coating steps. A final "stop" step is inserted
        at the end to bring the rotor to a halt.

        Args:
            recipe (SpincoatRecipe): recipe of spincoating steps + drop times

        Returns:
            record: dictionary of recorded spincoating process.
        """

        sample = self.maestro.samples[task["sample"]]
        recipe = sample["spincoat_recipe"]
        # time.sleep(recipe["duration"] / speedup_factor)
        await asyncio.sleep(recipe["duration"] / speedup_factor)
        # solution_dropped = False
        # antisolvent_dropped = False
        # record = {}

        # self.spincoater.start_logging()
        # spincoating_in_progress = True
        # t0 = self.nist_time()
        # tnext = 0
        # for start_time, (rpm, acceleration, duration) in zip(
        #     recipe.start_times, recipe.steps
        # ):
        #     tnext += start_time
        #     tnow = self.nist_time() - t0  # time relative to recipe start
        #     while (
        #         tnow <= tnext
        #     ):  # loop and check for drop times until next spin step is reached
        #         if not solution_dropped and tnow >= recipe.solution_droptime:
        #             self.liquidhandler.drop_perovskite()
        #             solution_dropped = True
        #             record["solution_drop"] = tnow
        #         if not antisolvent_dropped and tnow >= recipe.antisolvent_droptime:
        #             self.liquidhandler.drop_antisolvent()
        #             antisolvent_dropped = True
        #             record["antisolvent_drop"] = tnow
        #         time.sleep(0.1)

        #     self.spincoater.set_rpm(rpm=rpm, acceleration=acceleration)

        # self.spincoater.stop()
        # record.update(self.spincoater.finish_logging())

        # sample["spincoat_recipe"]["record"] = record


class Worker_Characterization(WorkerTemplate):
    def __init__(self, maestro):
        super().__init__(maestro=maestro)
        self.functions = {
            "characterize": partial(self.pause, 60 * 2.5 / speedup_factor),
        }

    def pause(self, t, task):
        time.sleep(t)


class Maestro:
    def __init__(self):
        self.gantry = None
        self.gripper = None
        self.spincoater = None
        self.characterization = None
        self.liquidhandler = None

        # Labware
        self.hotplates = {"HotPlate1": None}
        self.storage = {"SampleTray1": None}

        # Status
        self.samples = {}

        # worker thread coordination
        self.threadpool = ThreadPoolExecutor(max_workers=40)
        self.pending_tasks = []
        self.completed_tasks = {}
        self.lock_pendingtasks = Lock()
        self.lock_completedtasks = Lock()

        self.workers = {
            "gantry_gripper": Worker_GantryGripper(self),
            "spincoater_lh": Worker_SpincoaterLiquidHandler(self),
            "characterization": Worker_Characterization(self),
            "hotplates": Worker_Hotplate(self, n_workers=25),
            "storage": Worker_Storage(self, n_workers=45),
        }

    def load_netlist(self, filepath):
        self.samples, self.tasks = load_netlist(filepath)

    def make_background_event_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._keep_loop_running())

    async def _keep_loop_running(self):
        while self.working:
            await asyncio.sleep(1)

    def run(self):
        self.working = True
        self.thread = Thread(target=self.make_background_event_loop)
        self.thread.start()  # generates asyncio event loop in background thread (self.loop)
        time.sleep(0.5)
        # self.loop = asyncio.new_event_loop()
        self.loop.set_debug(True)
        self.t0 = self.nist_time()

        for worker in self.workers.values():
            worker.prime(loop=self.loop)
        for t in self.tasks:
            assigned = False
            t["start"] /= speedup_factor
            for workername, worker in self.workers.items():
                if t["task"] in worker.functions:
                    worker.add_task(t)
                    assigned = True
                    continue
            if not assigned:
                raise Exception(f"No worker assigned to task {t['task']}")

        for worker in self.workers.values():
            worker.start()
        # self.loop.run_forever()

    def nist_time(self):
        return time.time()


def main():
    maestro = Maestro()
    maestro.load_netlist("maestronetlist.json")
    maestro.run()
