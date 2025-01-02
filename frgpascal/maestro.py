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
import numpy as np
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
from frgpascal.hardware.switchbox import Switchbox
from frgpascal.analysis.processing import load_all

from frgpascal.workers import (
    Worker_Hotplate,
    Worker_Storage,
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_SpincoaterLiquidHandler,
)

from frgpascal.closedloop.websocket import Server
from frgpascal.hardware.helpers import get_ot2_ip

from frgpascal.hardware.characterizationline import CharacterizationLine


MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardware", "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)

ROOTDIR = "C:\\Users\\Admin\\Desktop\\PASCAL_Runs"


class MaestroServer(Server):
    """
    Websocket server from which Maestro can send and receive messages

    This class is only used when Maestro is controlled externally (ie for active learning)
    """

    def __init__(self, maestro):
        self.maestro = maestro
        super().__init__()

    def _process_message(self, message: str):
        options = {
            "set_start_time": self.set_start_time,
            "protocol": self.add_protocol,
            "get_experiment_directory": self.share_experiment_directory,
            "set_hotplate_setpoint": self.set_hotplate_setpoint,
        }

        d = json.loads(message)
        func = options[d.pop("type")]
        func(d)

    def set_start_time(self, d: dict):
        """Update the start time for the current run"""
        self.maestro.t0 = d["nist_time"]

    def add_protocol(self, sample_dict: dict):
        """Add a protocol to the maestro workers"""
        for t in sample_dict["worklist"]:
            assigned = False
            for workername, worker in self.maestro.workers.items():
                if t["name"] in worker.functions:
                    worker.add_task(t)
                    assigned = True
                    self.maestro.tasks.append(t)
                    continue
            if not assigned:
                raise Exception(f"No worker assigned to task {t['name']}")
        samplename = sample_dict["name"]
        self.maestro.samples[samplename] = sample_dict

    def share_experiment_directory(self, d: dict):
        """Share the experiment directory with the active learner"""
        msg_dict = {
            "type": "set_experiment_directory",
            "path": self.maestro.experiment_folder,
        }
        msg = json.dumps(msg_dict)
        self.send(msg)

    def set_hotplate_setpoint(self, d: dict):
        """Set the hotplate setpoint"""
        hp = self.maestro.hotplates[d["hotplate_name"]]
        hp.controller.setpoint = d["setpoint"]
        print(f"Maestro Client remotely set {d['hotplate_name']} to {d['setpoint']} C")


class Maestro:
    def __init__(
        self,
        samplewidth: float = 10,
    ):
        """Initialize Maestro, which coordinates all the PASCAL hardware

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

        # Labware
        self.hotplates = {
            "Hotplate1": HotPlate(
                name="Hotplate1",
                version="hotplate_frg4inch",
                gantry=self.gantry,
                gripper=self.gripper,
                id=1,
                p0=constants["hotplates"]["hp1"]["p0"],
            ),
            "Hotplate2": HotPlate(
                name="Hotplate2",
                version="hotplate_frg4inch",
                gantry=self.gantry,
                gripper=self.gripper,
                id=2,
                p0=constants["hotplates"]["hp2"]["p0"],
            ),
            "Hotplate3": HotPlate(
                name="Hotplate3",
                version="hotplate_frg4inch",
                gantry=self.gantry,
                gripper=self.gripper,
                id=3,
                p0=constants["hotplates"]["hp3"]["p0"],
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

        self.spincoater = SpinCoater(
            gantry=self.gantry,
            switch=self.switchbox.Switch(constants["spincoater"]["switchindex"]),
        )

        ### Workers to run tasks in parallel
        self.workers = {
            "gantry_gripper": Worker_GantryGripper(maestro=self),
            "spincoater_lh": Worker_SpincoaterLiquidHandler(maestro=self),
            "characterization": Worker_Characterization(maestro=self),
            "hotplates": Worker_Hotplate(
                maestro=self,
                capacity=sum([hp.capacity for hp in self.hotplates.values()]),
            ),
            "storage": Worker_Storage(
                maestro=self,
                capacity=sum([hp.capacity for hp in self.storage.values()]),
            ),
        }

        self._load_calibrations()  # load coordinate calibrations for labware
        self.__calibrate_time_to_nist()  # for sync with other hardware
        # Status
        self.samples = {}
        self.tasks = []
        self.lock_pendingtasks = Lock()
        self.lock_completedtasks = Lock()
        self.t0 = None
        self._under_external_control = False

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

    @property
    def experiment_time(self):
        if self.t0 is None:
            raise Exception("Experiment has not started!")
        return self.nist_time - self.t0

    @property
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

    def open_to_width(self, width):
        self.gripper.open(
            width, slow=False
        )  # slow to prevent sample position shifting upon release

    def open_to_pwm(self, pwm):
        self.gripper.open_pwm(pwm)

    def catch(self, from_spincoater=False):
        """
        Close gripper barely enough to pick up sample
        """
        caught_successfully = False
        catch_attempts = self.CATCHATTEMPTS

        while not caught_successfully and catch_attempts > 0:
            if from_spincoater or catch_attempts != self.CATCHATTEMPTS:
                self.gripper.close(slow=True)
            if from_spincoater and self.TWISTOFF:
                self.spincoater.twist_off()
                self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
                self.spincoater.lock()
            self.gripper.open(self.SAMPLEWIDTH - 2)
            # self.gripper.open(self.SAMPLEWIDTH - 1)
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
        if from_spincoater:
            self.spincoater.idle()  # no need to hold chuck at registered position once sample is removed

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

    def get_gripper_load(self):
        time.sleep(0.5)  # wait for gripper to complete motion
        self.gripper.write("l")
        with self.gripper._lock:
            load = float(self.gripper._handle.readline())
        return load

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
            wait_for_vacuum_thread = Thread(
                target=time.sleep, args=(self.spincoater.VACUUM_DISENGAGEMENT_TIME,)
            )
            lock_spincoater_thread = Thread(target=self.spincoater.lock)
            self.spincoater.vacuum_off()
            wait_for_vacuum_thread.start()  # wait for vacuum to disengage
            lock_spincoater_thread.start()  # move the spincoater to registered position
            self.gantry.moveto(p1, zhop=True)  # move to the pickup position
            wait_for_vacuum_thread.join()
            lock_spincoater_thread.join()
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
            lock_spincoater_thread = Thread(target=self.spincoater.lock)
            lock_spincoater_thread.start()  # move the spincoater to registered position
            self.gantry.moveto(x=p2[0], y=p2[1], z=p2[2], zhop=True)
            lock_spincoater_thread.join()
            self.spincoater.vacuum_on()
            self.gantry.moveto(
                x=p2[0], y=p2[1], z=p2[2] - 0.4, zhop=False
            )  # overshoot z to press sample onto o-ring on spincoater chuck
        else:
            self.gantry.moveto(
                p2, zhop=zhop
            )  # if not dropped, move to the final position

        # time.sleep(2)
        self.release()  # drop the sample

        self.gantry.moverel(
            z=self.gantry.ZHOP_HEIGHT
        )  # move up a bit, mostly to avoid resting gripper on hotplate

        # self.gripper.close()  # fully close gripper to reduce servo strain
        if all([a == b for a, b in zip(p2, self.spincoater())]):
            self.gantry._transition_to_frame(
                "workspace"
            )  # move gantry out of the liquid handler
            self.spincoater.idle()  # dont actively hold chuck in registered position

    ### Batch Sample Execution
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
        if self._under_external_control:
            # if under external control, the pending tasklist might be exhausted before experiment ends
            while self.working:
                await asyncio.sleep(1)
            # once we manually set `self.working = False`, wait for pending tasks to be exhausted
            while len(self.pending_tasks) > 0:
                await asyncio.sleep(1)
            experiment_completed = True
        else:
            # if under maestro control, experiment is done when the tasklist is exhausted!
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
                        if len(self.completed_tasks) == len(self.tasks):
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

    def _load_worklist(self, filepath):
        with open(filepath, "r") as f:
            worklist = json.load(f)
        # self.tasks = worklist["tasks"]
        self.samples = worklist["samples"]
        self.tasks = []
        for details in self.samples.values():
            self.tasks.extend(details["worklist"])
        self.tasks.sort(key=lambda t: t["start"])

        for hp_name, temperature in worklist["hotplate_setpoints"].items():
            self.hotplates[hp_name].controller.setpoint = temperature
            print(f"Hotplate {hp_name} set to {temperature:.1f}C")
        return worklist["name"]
        # self._characterization_baselines_required = worklist["baselines_required"]

    def _set_up_experiment_folder(self, name):
        todays_date = datetime.datetime.now().strftime("%Y%m%d")
        folder_name = f"{todays_date}_{name}"
        suffix = ""
        idx = 0
        while True:
            folder = os.path.join(ROOTDIR, f"{folder_name}{suffix}")
            if os.path.exists(folder):
                idx += 1
                suffix = f"_{idx}"
            else:
                break
        os.mkdir(folder)
        print(f"Experiment folder created at {folder}")
        self.characterization.set_directory(os.path.join(folder, "Characterization"))
        self.experiment_folder = folder
        self.logger.setLevel(logging.DEBUG)
        self._fh = logging.FileHandler(
            os.path.join(self.experiment_folder, f"{folder_name}.log")
        )
        self._sh = logging.StreamHandler(sys.stdout)
        self._sh.setLevel(logging.INFO)
        fh_formatter = logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s",
            datefmt="%m/%d/%Y %I:%M:%S %p",
        )
        sh_formatter = logging.Formatter(
            "%(asctime)s %(message)s",
            datefmt="%I:%M:%S",
        )
        self._fh.setFormatter(fh_formatter)
        self._sh.setFormatter(sh_formatter)
        self.logger.addHandler(self._fh)
        self.logger.addHandler(self._sh)

        return folder

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

    def turn_off_hotplates(self):
        for hp in self.hotplates.values():
            hp.controller.setpoint = 0

    def load_netlist(self, filepath: str):
        experiment_name = self._load_worklist(filepath)
        self._set_up_experiment_folder(experiment_name)

    def run(self):
        if len(self.samples) == 0:
            raise Exception("No samples loaded, did you forget to run .load_netlist()?")
        self._experiment_checklist()
        self.pending_tasks = []
        self.completed_tasks = {}
        self.liquidhandler.server.ip = get_ot2_ip()

        self._start_loop()
        self.t0 = self.nist_time

        for worker in self.workers.values():
            worker.prime(loop=self.loop)
        for task in self.tasks:
            assigned = False
            for workername, worker in self.workers.items():
                if task["name"] in worker.functions:
                    worker.add_task(task)
                    assigned = True
                    continue
            if not assigned:
                raise Exception(f"No worker assigned to task {task['name']}")

        for worker in self.workers.values():
            worker.start()

    def stop(self):
        self.working = False
        # clean up the experiment, save log of actual timings
        for hp in self.hotplates.values():
            hp.controller.setpoint = 0
        with open(
            os.path.join(self.experiment_folder, "maestro_sample_log.json"), "w"
        ) as f:
            json.dump(self.samples, f)
        metrics, _ = load_all(datadir=self.characterization.rootdir)
        metrics.to_csv(
            os.path.join(self.experiment_folder, "fitted_characterization_metrics.csv")
        )

        for w in self.workers.values():
            w.stop_workers()
        if self.liquidhandler.server.ip is not None:
            self.liquidhandler.mark_completed()  # tell liquid handler to complete the protocol.

        self.logger.info("Finished experiment, stopping now.")

        for h in self.logger.handlers:
            self.logger.removeHandler(h)

        print("Maestro stopped!")
        self.gantry.movetoclear()
        # self.thread.join()

    def __del__(self):
        if self.working:
            self.stop()
        self.liquidhandler.server.stop()

    ### External driver to interface with BO program
    async def _instruction_monitor(self, instruction_directory):
        while self.working:
            new_tasks = []
            fids = [
                os.path.join(instruction_directory, f)
                for f in os.listdir(instruction_directory)
                if f not in self.read_protocol_files
            ]
            for filepath in fids:
                with open(filepath, "r") as f:
                    this_protocol = json.load(f)
                new_tasks += this_protocol["tasks"]
                self.samples += this_protocol["samples"]

            if len(new_tasks) > 0:
                new_tasks.sort(key=lambda task: task["start"])
                for t in new_tasks:
                    assigned = False
                    for workername, worker in self.workers.items():
                        if t["task"] in worker.functions:
                            worker.add_task(t)
                            assigned = True
                            self.tasks.append(t)
                            continue
                    if not assigned:
                        raise Exception(f"No worker assigned to task {t['task']}")
            await asyncio.sleep(0.5)

    def run_externalcontrol(self, name, ot2_ip):
        self._experiment_checklist()
        self.working = True
        self._under_external_control = True

        self.liquidhandler.server.ip = ot2_ip
        # self.read_protocol_files = []
        self.pending_tasks = []
        self.completed_tasks = {}
        folder = self._set_up_experiment_folder(name)
        self._start_loop()

        for worker in self.workers.values():
            worker.prime(loop=self.loop)
            worker.start()

        self.server = MaestroServer(maestro=self)  # open for external commands
