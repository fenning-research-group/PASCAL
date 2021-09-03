from frgpascal.hardware.switchbox import Switchbox
import os
import sys
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
import time
import yaml
import json
import ntplib
import asyncio
import datetime
import logging

from frgpascal.hardware.spincoater import SpinCoater
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper
from frgpascal.hardware.liquidhandler import OT2
from frgpascal.hardware.hotplate import HotPlate
from frgpascal.hardware.sampletray import SampleTray
from frgpascal.hardware.characterizationline import (
    CharacterizationAxis,
    CharacterizationLine,
)
from frgpascal.experimentaldesign.recipes import SpincoatRecipe, AnnealRecipe, Sample
from frgpascal.workers import (
    Worker_Hotplate,
    Worker_Storage,
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_SpincoaterLiquidHandler,
)

# from frgpascal.hardware.characterizationline import CharacterizationLine


MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardware", "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)

ROOTDIR = "C:\\Users\\Admin\\Desktop\\PASCAL Runs"


class Maestro:
    def __init__(
        self,
        samplewidth: float = 10,
    ):
        """Initialze Maestro, which coordinates all the PASCAL hardware

        Args:
            numsamples (int): number of substrates loaded in sampletray
            samplewidth (float, optional): width of the substrates (mm). Defaults to 10 (ie 1 cm).
        """

        # Constants
        self.logger = logging.getLogger("PASCAL")
        self.SAMPLEWIDTH = samplewidth  # mm
        self.SAMPLETOLERANCE_PICK = constants["gripper"][
            "extra_opening_width_pick"
        ]  # mm extra opening width
        self.SAMPLETOLERANCE_PLACE = constants["gripper"][
            "extra_opening_width_place"
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
        self.switchbox = Switchbox()
        self.spincoater = SpinCoater(
            gantry=self.gantry,
            switch=self.switchbox.Switch(constants["spincoater"]["switchindex"]),
        )
        self.characterization = CharacterizationLine(
            gantry=self.gantry, rootdir=ROOTDIR, switchbox=self.switchbox
        )
        self.liquidhandler = OT2()

        # Labware
        self.hotplates = {
            "HotPlate1": HotPlate(
                name="Hotplate1",
                version="hotplate_SCILOGEX_tighter",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["hotplate"]["p0"],
            )
        }
        self.storage = {
            "Tray1": SampleTray(
                name="SampleTray1",
                version="storage_v3",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["sampletray"]["p0"],
            )
        }
        # Stock Solutions

        self._load_calibrations()  # load coordinate calibrations for labware
        self.__calibrate_time_to_nist()  # for sync with other hardware
        # Status
        self.samples = {}
        self.tasks = {}

        # worker thread coordination
        self.threadpool = ThreadPoolExecutor(max_workers=40)

    ### Time Synchronization with NIST
    def __calibrate_time_to_nist(self):
        client = ntplib.NTPClient()
        response = None
        while response is None:
            try:
                response = client.request("europe.pool.ntp.org", version=3)
            except:
                pass
        self.__local_nist_offset = response.tx_time - time.time()

    def nist_time(self):
        return time.time() + self.__local_nist_offset

    def calibrate(self):
        """Prompt user to fine tune the gantry positions for all hardware components"""
        components = [self.spincoater, self.characterization.axis]
        components += list(self.hotplates.values())
        components += list(self.storage.values())
        for component in [
            *self.hotplates.values(),
            *self.storage.values(),
            self.spincoater,
            self.characterization.axis,
        ]:
            # self.release()  # open gripper to open width
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
            *self.hotplates.values(),
            *self.storage.values(),
            self.spincoater,
            self.characterization.axis,
        ]:  # , self.spincoater]:
            component._load_calibration()  # REFACTOR #4 make the hardware calibrations save to a yaml instead of pickle file

    ### Compound Movements

    def catch(self):
        """
        Close gripper barely enough to pick up sample, not all the way to avoid gripper finger x float
        """
        caught_successfully = False
        catch_attempts = self.CATCHATTEMPTS
        while not caught_successfully and catch_attempts > 0:
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
                catch_attempts -= 1
                # lets jog the gripper position and try again.
                self.gripper.close()
                self.open_to_catch()
                # self.gripper.open(self.SAMPLEWIDTH + self.SAMPLETOLERANCE_PICK, slow=False)
                # self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
                self.gantry.moverel(z=-self.gantry.ZHOP_HEIGHT)

        if not caught_successfully:
            self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
            self.gripper.close()
            raise ValueError("Failed to pick up sample!")

    def open_to_catch(self):
        """
        Open gripper quickly before picking up a sample
        """
        self.gripper.open(
            self.SAMPLEWIDTH + self.SAMPLETOLERANCE_PICK, slow=False
        )  # slow to prevent sample position shifting upon release

    def release(self):
        """
        Open gripper slowly to release a sample without jogging position too much
        """
        self.gripper.open(
            self.SAMPLEWIDTH + self.SAMPLETOLERANCE_PLACE, slow=True
        )  # slow to prevent sample position shifting upon release

    def idle_gantry(self):
        """Move gantry to the idle position. This is primarily to provide cameras a clear view"""
        self.gantry.moveto(self.IDLECOORDINATES)
        self.gripper.close()

    def transfer(self, p1, p2, zhop=True):
        self.open_to_catch()  # open the grippers
        self.gantry.moveto(p1, zhop=zhop)  # move to the pickup position
        self.catch()  # pick up the sample. this function checks to see if gripper picks successfully
        # self.gantry.moveto(
        #     x=p2[0], y=p2[1], z=p2[2] + 5, zhop=zhop
        # )  # move just above destination
        # if self.gripper.is_under_load():
        #     raise ValueError("Sample dropped in transit!")
        self.gantry.moveto(p2, zhop=True)  # if not dropped, move to the final position
        self.release()  # drop the sample
        self.gantry.moverel(
            z=self.gantry.ZHOP_HEIGHT
        )  # move up a bit, mostly to avoid resting gripper on hotplate
        # self.gripper.close()  # fully close gripper to reduce servo strain

    ### Batch Sample Execution
    def _load_netlist(self, filepath):
        with open(filepath) as f:
            netlist = json.load(f)
        self.tasks = netlist["tasks"]
        self.samples = netlist["samples"]

    def make_background_event_loop(self):
        def exception_handler(loop, context):
            print("Exception raised in Maestro loop")
            self.logger.error(json.dumps(context))

        self.loop = asyncio.new_event_loop()
        self.loop.set_exception_handler(exception_handler)
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._keep_loop_running())

    async def _keep_loop_running(self):
        experiment_started = False
        experiment_completed = False
        while self.working:
            if (
                not experiment_started
            ):  # wait for the task list to start being populated
                with self.lock_pendingtasks:
                    if len(self.pending_tasks) > 0:
                        experiment_started = True
                await asyncio.sleep(30)
            elif not experiment_completed:
                with self.lock_pendingtasks:
                    if len(self.pending_tasks) == 0:
                        experiment_completed = True
                await asyncio.sleep(5)
            else:
                break
        self.stop()

    def _start_loop(self):
        self.working = True
        self.thread = Thread(target=self.make_background_event_loop)
        self.thread.start()  # generates asyncio event loop in background thread (self.loop)
        time.sleep(0.5)
        # self.loop = asyncio.new_event_loop()
        # self.loop.set_debug(True)

    def _set_up_experiment_folder(self, name):
        todays_date = datetime.datetime.now().strftime("%Y%m%d")
        folder_name = f"{todays_date}_{name}"
        folder = os.path.join(ROOTDIR, folder_name)
        os.mkdir(folder)
        self.characterization.set_directory(folder)
        self.experiment_folder = folder
        self.logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(
            os.path.join(self.experiment_folder, f"{folder_name}.log")
        )
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        fh_formatter = logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s",
            datefmt="%m/%d/%Y %I:%M:%S %p",
        )
        sh_formatter = logging.Formatter(
            "%(asctime)s %(message)s",
            datefmt="%I:%M:%S",
        )
        fh.setFormatter(fh_formatter)
        sh.setFormatter(sh_formatter)
        self.logger.addHandler(fh)
        self.logger.addHandler(sh)

    def run(self, filepath, name, ot2_ip):
        if not self.characterization._calibrated:
            raise Exception(
                "Cannot start until characterization line has been calibrated!"
            )
        self.liquidhandler.server.ip = ot2_ip
        # self.liquidhandler.server.start(ip=ot2_ip)
        self.pending_tasks = []
        self.completed_tasks = {}
        self.lock_pendingtasks = Lock()
        self.lock_completedtasks = Lock()
        self._load_netlist(filepath)
        self._set_up_experiment_folder(name)

        self.workers = {
            "gantry_gripper": Worker_GantryGripper(self),
            "spincoater_lh": Worker_SpincoaterLiquidHandler(self),
            "characterization": Worker_Characterization(self),
            "hotplates": Worker_Hotplate(
                self, n_workers=25
            ),  # TODO dont hardcode hotplate workers
            "storage": Worker_Storage(
                self, n_workers=45
            ),  # TODO dont hardcode storage workers
        }

        self._start_loop()
        # self.loop = asyncio.new_event_loop()
        # self.loop.set_debug(True)
        self.t0 = self.nist_time()

        for worker in self.workers.values():
            worker.prime(loop=self.loop)
        for t in self.tasks:
            assigned = False
            for workername, worker in self.workers.items():
                if t["task"] in worker.functions:
                    worker.add_task(t)
                    assigned = True
                    continue
            if not assigned:
                raise Exception(f"No worker assigned to task {t['task']}")

        for worker in self.workers.values():
            worker.start()

    def stop(self):
        self.working = False
        self.liquidhandler.server.mark_completed()  # tell liquid handler to complete the protocol.
        self.thread.join()
        # clean up the experiment, save log of actual timings
        with open(
            os.path.join(self.experiment_folder, "maestro_sample_log.json"), "w"
        ) as f:
            json.dump(self.samples, f)

    def __del__(self):
        if self.working:
            self.stop()
        self.liquidhandler.server.stop()
