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
from natsort import natsorted
from tqdm import tqdm
from warnings import warn

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
from frgpascal.workers import (
    Worker_Hotplate,
    Worker_Storage,
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_SpincoaterLiquidHandler,
)

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
        self.CATCHATTEMPTS = constants["gripper"][
            "catch_attempts"
        ]  # number of times to try picking up a sample before erroring out
        self.TWISTOFF = True
        # Workers
        self.gantry = Gantry()
        self.gripper = Gripper()
        self.switchbox = Switchbox()
        self.characterization = CharacterizationLine(
            gantry=self.gantry, rootdir=ROOTDIR, switchbox=self.switchbox
        )
        self.liquidhandler = OT2()
        self.spincoater = SpinCoater(
            gantry=self.gantry,
            switch=self.switchbox.Switch(constants["spincoater"]["switchindex"]),
        )

        # Labware
        self.hotplates = {
            "Hotplate1": HotPlate(
                name="Hotplate1",
                version="hotplate_FRGv1",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["hotplates"]["hp1"]["p0"],
            ),
            "Hotplate2": HotPlate(
                name="Hotplate2",
                version="hotplate_FRGv1",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["hotplates"]["hp2"]["p0"],
            ),
            "Hotplate3": HotPlate(
                name="Hotplate3",
                version="hotplate_FRGv1",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["hotplate"]["hp3"]["p0"],
            ),
        }

        self.storage = {
            "Tray1": SampleTray(
                name="Tray1",
                version="storage_v3",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["sampletray"]["p1"],
            ),
            "Tray2": SampleTray(
                name="Tray2",
                version="storage_v3",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["sampletray"]["p2"],
            ),
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
        t0 = time.time()
        while response is None:
            try:
                response = client.request("europe.pool.ntp.org", version=3)
            except:
                pass
            if time.time() - t0 >= 10:
                warn("Could not get NIST time!")
                return
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

    def open_to_catch(self):
        """
        Open gripper quickly before picking up a sample
        """
        self.gripper.open(
            self.SAMPLEWIDTH + self.SAMPLETOLERANCE_PICK, slow=False
        )  # slow to prevent sample position shifting upon release

    def catch(self, from_spincoater=False):
        """
        Close gripper barely enough to pick up sample
        """
        caught_successfully = False
        catch_attempts = self.CATCHATTEMPTS
        while not caught_successfully and catch_attempts > 0:
            self.gripper.close(slow=True)
            if from_spincoater and self.TWISTOFF:
                self.spincoater.twist_off()
                self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
                self.spincoater.lock()
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

    def release(self):
        """
        Open gripper slowly to release a sample without jogging position too much
        """
        self.gripper.open(
            self.SAMPLEWIDTH + self.SAMPLETOLERANCE_PLACE, slow=True
        )  # slow to prevent sample position shifting upon release

    def idle_gantry(self):
        """Move gantry to the idle position. This is primarily to provide cameras a clear view"""
        self.gantry.movetoidle()
        self.gripper.close()

    def transfer(self, p1, p2, zhop=True):
        """Move a sample from one location (source) to another (destination)

        Args:
            p1: coordinates of source location
            p2: cooordinates of destination location
            zhop (bool, optional): Whether to "hop" in z to avoid collisions. Defaults to True.

        Raises:
            ValueError: Sample has been dropped during transit
        """
        self.open_to_catch()  # open the grippers
        if all(
            [a == b for a, b in zip(p1, self.spincoater())]
        ):  # moving off of the spincoater
            off_thread = Thread(
                target=time.sleep, args=(self.spincoater.VACUUM_DISENGAGEMENT_TIME,)
            )
            self.spincoater.vacuum_off()
            off_thread.start()
            self.gantry.moveto(p1, zhop=True)  # move to the pickup position
            off_thread.join()
            from_spincoater = True
        else:
            self.gantry.moveto(p1, zhop=zhop)
            from_spincoater = False
        self.catch(
            from_spincoater=from_spincoater
        )  # pick up the sample. this function checks to see if gripper picks successfully

        ### Code for drop check, currently not being used
        # self.gantry.moveto(
        #     x=p2[0], y=p2[1], z=p2[2] + 5, zhop=zhop
        # )  # move just above destination
        # if self.gripper.is_under_load():
        #     raise ValueError("Sample dropped in transit!")

        if all(
            [a == b for a, b in zip(p2, self.spincoater())]
        ):  # moving onto the spincoater
            self.gantry.moveto(x=p2[0], y=p2[1], z=p2[2] + 5, zhop=True)
            self.spincoater.vacuum_on()
            self.gantry.moveto(
                x=p2[0], y=p2[1], z=p2[2] - 0.4, zhop=False
            )  # overshoot z to press sample onto o-ring on spincoater chuck
        else:
            self.gantry.moveto(
                p2, zhop=zhop
            )  # if not dropped, move to the final position
        self.release()  # drop the sample
        self.gantry.moverel(
            z=self.gantry.ZHOP_HEIGHT
        )  # move up a bit, mostly to avoid resting gripper on hotplate
        # self.gripper.close()  # fully close gripper to reduce servo strain
        if all([a == b for a, b in zip(p2, self.spincoater())]):
            self.gantry._transition_to_frame(
                "workspace"
            )  # move gantry out of the liquid handler

    def batch_characterize(self, name, tray_maxslots={}):
        """
        Characterize a list of samples.
        Creates an experiment folder to save data, filenames by tray-slot

        Parameters
            tray_maxslots (dict): a dictionary of tray names and the highest index filled

                    ie: tray_maxslots = {'SampleTray1': 'A5'} will measure samples A1, A2, A3, A4, A5
        """
        self._experiment_checklist(characterization_only=True)
        self._set_up_experiment_folder(name)

        if any([tray not in self.storage for tray in tray_maxslots]):
            raise ValueError("Invalid tray specified!")

        samples_to_characterize = []
        for tray, maxslot in tray_maxslots.items():
            if maxslot not in self.storage[tray]._coordinates:
                raise ValueError(f"{maxslot} does not exist in tray {tray}!")
            for slot in natsorted(self.storage[tray]._coordinates.keys()):
                samples_to_characterize.append((tray, slot))
                if slot == tray_maxslots[tray]:
                    break  # last sample to measure in this tray

        for (tray, slot) in tqdm(
            samples_to_characterize, desc="Batch Characterization"
        ):
            self.transfer(self.storage[tray](slot), self.characterization.axis())
            self.characterization.run(f"{tray}-{slot}")
            self.transfer(self.characterization.axis(), self.storage[tray](slot))

    def batch_characterize(self, name, tray_maxslots={}):
        """
        Characterize a list of samples.
        Creates an experiment folder to save data, filenames by tray-slot

        Parameters
            tray_maxslots (dict): a dictionary of tray names and the highest index filled

                    ie: tray_maxslots = {'SampleTray1': 'A5'} will measure samples A1, A2, A3, A4, A5
        """
        self._experiment_checklist(characterization_only=True)
        self._set_up_experiment_folder(name)

        if any([tray not in self.storage for tray in tray_maxslots]):
            raise ValueError("Invalid tray specified!")

        samples_to_characterize = []
        for tray, maxslot in tray_maxslots.items():
            if maxslot not in self.storage[tray]._coordinates:
                raise ValueError(f"{maxslot} does not exist in tray {tray}!")
            for slot in natsorted(self.storage[tray]._coordinates.keys()):
                samples_to_characterize.append((tray, slot))
                if slot == tray_maxslots[tray]:
                    break  # last sample to measure in this tray

        for (tray, slot) in tqdm(
            samples_to_characterize, desc="Batch Characterization"
        ):
            self.transfer(self.storage[tray](slot), self.characterization.axis())
            self.characterization.run(f"{tray}-{slot}")
            self.transfer(self.characterization.axis(), self.storage[tray](slot))

    ### Batch Sample Execution
    def _load_worklist(self, filepath):
        with open(filepath) as f:
            worklist = json.load(f)
        self.tasks = worklist["tasks"]
        self.samples = worklist["samples"]

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
        if experiment_completed == True:
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

    def _experiment_checklist(self, characterization_only=False):
        """prompt user to go through checklist to ensure that
        all hardware is set properly for PASCAL to run

        """

        def prompt_for_yes(s):
            response = input(s)
            if response not in ["y", "Y"]:
                raise Exception("Checklist failed!")

        if not self.characterization._calibrated:
            raise Exception(
                "Cannot start until characterization line has been calibrated!"
            )

        prompt_for_yes("Is the transmission lamp on? (y/n)")
        prompt_for_yes("Is the sample holder(s) loaded and in place? (y/n)")
        if not characterization_only:
            prompt_for_yes("Is the vacuum pump on? (y/n)")
            prompt_for_yes(
                "Are the vials loaded into the liquid handler with the caps off? (y/n)"
            )
            prompt_for_yes(
                "Are there fresh pipette tips loaded into the liquid handler (starting with deck slot 7)? (y/n)"
            )
            prompt_for_yes(
                "Has the liquid handler listener protocol been run up to the waiting point? (y/n)"
            )

        # if we make it this far, checklist has been passed

    def run(self, filepath, name, ot2_ip):
        self._experiment_checklist()

        self.liquidhandler.server.ip = ot2_ip
        # self.liquidhandler.server.start(ip=ot2_ip)
        self.pending_tasks = []
        self.completed_tasks = {}
        self.lock_pendingtasks = Lock()
        self.lock_completedtasks = Lock()
        self._load_worklist(filepath)
        self._set_up_experiment_folder(name)

        self.workers = {
            "gantry_gripper": Worker_GantryGripper(maestro=self),
            "spincoater_lh": Worker_SpincoaterLiquidHandler(maestro=self),
            "characterization": Worker_Characterization(maestro=self),
        }

        for hpname, hp in self.workers.items():
            self.workers[hpname] = Worker_Hotplate(maestro=self, n_workers=hp._capacity)
        for stname, st in self.storage.items():
            self.workers[stname] = Worker_Storage(maestro=self, n_workers=st._capacity)

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
        # clean up the experiment, save log of actual timings
        with open(
            os.path.join(self.experiment_folder, "maestro_sample_log.json"), "w"
        ) as f:
            json.dump(self.samples, f)
        for w in self.workers.values():
            w.stop_workers()
        self.liquidhandler.mark_completed()  # tell liquid handler to complete the protocol.
        self.thread.join()

    def __del__(self):
        if self.working:
            self.stop()
        self.liquidhandler.server.stop()
