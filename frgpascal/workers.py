from threading import Thread, Lock
from queue import Queue
from abc import ABC, abstractmethod
import time

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
    def __init__(self, maestro):
        self.maestro = maestro
        self.queue = Queue()
        self.functions = (
            {}
        )  # this must be filled in by each method to map tasks to functions

    def start(self):
        self.thread = Thread(target=self.worker)
        self.thread.start()

    def worker(self):
        """process items from the queue + keep the maestro lists updated"""
        while True:
            task = self.queue.get()  # blocking wait for next task
            if task is None:
                break  # None signals all tasks complete

            # wait for all previous tasks to complete
            with self.maestro.lock_pendingtasks:
                self.maestro.pending_tasks.append(task["taskid"])
            for precedent in task["preceding_tasks"]:
                with self.maestrto.lock_completedtasks:
                    found = precedent in self.maestro.completed_tasks
                if found:
                    continue
                else:
                    time.sleep(0.25)

            # wait for this task's target start time
            wait_for = (
                self.maestro.nist_time() - task["time"] - self.maestro.t0
            )  # how long to wait before executing
            if wait_for > 0:
                time.sleep(wait_for)

            # execute this task
            function = self.functions[task["function"]]
            function(*task["args"], **task["kwargs"])

            # update task lists
            with self.lock_completedtasks:
                self.completed_tasks["taskid"] = (
                    self.maestro.nist_time() - self.maestro.t0
                )
            with self.lock_pendingtasks:
                self.pending_tasks.remove(task["taskid"])


class Worker_GantryGripper(WorkerTemplate):
    def __init__(self, maestro, gantry: Gantry, gripper: Gripper):
        super().__init__(maestro=maestro)
        self.functions = {
            "moveto": gantry.moveto,
            "moverel": gantry.moverel,
            "open": gripper.open,
            "close": gripper.close,
            "transfer": maestro.transfer,
            "idle_gantry": maestro.idle_gantry,
        }


class Worker_SpincoaterLiquidHandler(WorkerTemplate):
    def __init__(self, maestro, spincoater: SpinCoater, liquidhandler: OT2):
        super().__init__(maestro=maestro)
        self.functions = {
            "vacuum_on": spincoater.vacuum_on,
            "vacuum_off": spincoater.vacuum_off,
            "set_rpm": spincoater.set_rpm,
            "stop": spincoater.stop,
            "start_logging": spincoater.start_logging,
            "finish_logging": spincoater.finish_logging,
            "aspirate_for_spincoating": liquidhandler.aspirate_for_spincoating,
            "aspirate_both_for_spincoating": liquidhandler.aspirate_both_for_spincoating,
            "stage_perovskite": liquidhandler.stage_perovskite,
            "stage_antisolvent": liquidhandler.stage_antisolvent,
            "drop_perovskite": liquidhandler.drop_perovskite,
            "drop_antisolvent": liquidhandler.drop_antisolvent,
            "clear_chuck": liquidhandler.clear_chuck,
            "cleanup": liquidhandler.cleanup,
            "spincoat": maestro.spincoat,
        }


class Worker_Characterization(WorkerTemplate):
    def __init__(
        self,
        maestro,
        characterizationline: CharacterizationLine,
        characterizationaxis: CharacterizationAxis,
    ):
        super().__init__(maestro=maestro)
        self.functions = {
            "run": characterizationline.run,
            "moveto": characterizationaxis.moveto,
            "moverel": characterizationaxis.moverel,
            "movetotransfer": characterizationaxis.movetotransfer,
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
