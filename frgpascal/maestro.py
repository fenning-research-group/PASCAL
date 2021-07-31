# from termios import error
import os
from threading import Thread, Lock
import time
import yaml
import ntplib

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
from frgpascal.experimentaldesign.recipes import SpincoatRecipe, AnnealRecipe, Sample
from frgpascal.workers import (
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_SpincoaterLiquidHandler,
)

# from frgpascal.hardware.characterizationline import CharacterizationLine


MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardware", "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class Maestro:
    def __init__(
        self,
        numsamples: int = 1,
        samplewidth: float = 10,
        rootdir="C:\\Users\\Admin\\Desktop\\20210719_Moses_UVOvsTime_v2withlaseronbottom",
    ):
        """Initialze Maestro, which coordinates all the PASCAL hardware

        Args:
            numsamples (int): number of substrates loaded in sampletray
            samplewidth (float, optional): width of the substrates (mm). Defaults to 10 (ie 1 cm).
        """

        # Constants
        self.SAMPLEWIDTH = samplewidth  # mm
        self.SAMPLETOLERANCE = constants["gripper"][
            "extra_opening_width"
        ]  # mm extra opening width
        self.IDLECOORDINATES = constants["gantry"][
            "idle_coordinates"
        ]  # where to move the gantry during idle times, mainly to avoid cameras.
        self.CATCHATTEMPTS = constants["gripper"][
            "catch_attempts"
        ]  # number of times to try picking up a sample before erroring out
        # Workers
        self.gantry = Gantry()
        self.gripper = Gripper()
        self.spincoater = SpinCoater(gantry=self.gantry)
        self.characterization = CharacterizationLine(
            gantry=self.gantry, rootdir=rootdir
        )
        self.liquidhandler = OT2()

        # Labware
        self.hotplates = {
            "HotPlate1": HotPlate(
                name="Hotplate1",
                version="hotplate_SCILOGEX",  # TODO #3 move the version details into a yaml file, define version in hardwareconstants instead.
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["hotplate"]["p0"],
            )
        }
        self.storage = {
            "SampleTray1": SampleTray(
                name="SampleTray1",
                version="storage_v1",  # TODO #3
                num=numsamples,  # number of substrates loaded
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["sampletray"]["p0"],
            )
        }
        # Stock Solutions

        self._load_calibrations()  # load coordinate calibrations for labware
        self.__calibrate_time_to_nist()  # for sync with other hardware
        # Status
        self.manifest = {}  # store all sample info, key is sample storage slot

        # worker thread coordination
        self.pending_tasks = []
        self.completed_tasks = {}
        self.lock_pendingtasks = Lock()
        self.lock_completedtasks = Lock()

    ### Time Synchronization with NIST
    def __calibrate_time_to_nist(self):
        client = ntplib.NTPClient()
        response = None
        while response is None:
            try:
                response = client.request("europe.pool.ntp.org", version=3)
            except:
                pass
        t_local = time.time()
        self.__local_nist_offset = response.tx_time - t_local

    def nist_time(self):
        return time.time() + self.__local_nist_offset

    def calibrate(self):
        """Prompt user to fine tune the gantry positions for all hardware components"""
        for component in [
            self.hotplate,
            self.storage,
            self.spincoater,
            self.characterization.axis,
        ]:
            self.release()  # open gripper to open width
            component.calibrate()

    def gohome(self):
        threads = []
        for task in [
            self.gantry.gohome,
            self.characterization.axis.gohome,
            # self.spincoater.connect,
        ]:
            thread = Thread(target=task)
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()

    def _load_calibrations(self):
        """Load previous gantry positions, assume that hardware hasn't moved since last time."""
        print(
            "Loading labware coordinate calibrations - if any labware has moved, be sure to .calibrate() it!"
        )
        for component in [
            self.hotplate,
            self.storage,
            self.spincoater,
            self.characterization.axis,
        ]:  # , self.spincoater]:
            component._load_calibration()  # REFACTOR #4 make the hardware calibrations save to a yaml instead of pickle file

    ### Physical Methods
    # Compound Movements

    ### Compound tasks

    def anneal(self, sample):
        time.sleep(sample["anneal_recipe"]["duration"])

    def cooldown(self, sample):
        time.sleep(180)  # TODO - make this a variable

    ### Workers
    ## Gantry + Gripper
    def gantry_gripper(self):
        """Consumer for tasks involving transfer of samples with gantry+gripper
        """
        tasklist = {
            "storage_to_spincoater": self.storage_to_spincoater,
            "spincoater_to_hotplate": self.spincoater_to_hotplate,
            "hotplate_to_storage": self.hotplate_to_storage,
            "storage_to_characterization": self.storage_to_characterization,
            "characterization_to_storage": self.characterization_to_storage,
        }
        while self.run_in_progress:
            start_time, task, precedent_taskids = await self.gantry_queue.get()
            time_until_start = self.t0_nist + start_time - self.nist_time()
            await asyncio.sleep(time_until_start)  # wait until start time
            for (
                precedent
            ) in precedent_taskids:  # wait until all preceding tasks are complete
                while precedent not in self.completed_tasks:
                    await asyncio.sleep(0.1)

            sample = task["sample"]
            func = tasklist[task["task"]]
            await func(sample)

        self.completed_tasks[task["taskid"]] = self.nist_time()
        self.gantry_queue.task_done()

    def run_list(self, tasklist):
        self.worker_gg = Worker_GantryGripper(
            maestro=self, gantry=self.gantry, gripper=self.gripper
        )
        self.worker_sclh = Worker_SpincoaterLiquidHandler(
            maestro=self, spincoater=self.spincoater, liquidhandler=self.liquidhandler
        )
        self.worker_cl = Worker_Characterization(
            maestro=self,
            characterizationline=self.characterization,
            characterizationaxis=self.characterization.axis,
        )

        queuedict = {
            "GantryGripper": self.worker_gg.queue,
            "SpincoaterLiquidHandler": self.worker_sclh.queue,
            "Characterization": self.worker_cl.queue,
        }

        for task in tasklist:
            queue = queuedict[task["worker"]]
            queue.put(task["contents"])

        self._t0 = self.nist_time()
        for worker in [self.worker_cl, self.worker_sclh, self.worker.gg]:
            self.start()

    def __del__(self):
        self.liquidhandler.server.stop()
