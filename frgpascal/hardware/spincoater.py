import odrive  # odrive documentation https://docs.odriverobotics.com/
from odrive.enums import *  # control/state enumerations
import serial
import time
import numpy as np
import os
import yaml
import threading
from frgpascal.hardware.helpers import get_port
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.switchbox import SingleSwitch
from datetime import datetime

MODULE_DIR = os.path.dirname(__file__)
CALIBRATION_DIR = os.path.join(MODULE_DIR, "calibrations")
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.Loader)

# spincoater_serial_number = constants["spincoater"]["serialid"]
# print(constants["spincoater"])


class SpinCoater:
    def __init__(self, gantry: Gantry, switch: SingleSwitch):
        """Initialize the spincoater control object

        Args:
                                        gantry (Gantry): PASCAL Gantry control object
                                        serial_number (str, optional): Serial number for spincoater arduino, used to find and connect to correct COM port. Defaults to "558383339323513140D1":str.
                                        p0 (tuple, optional): Initial guess for gantry coordinates to drop sample on spincoater. Defaults to (52, 126, 36):tuple.
        """
        # constants
        # if port is None:
        #     self.port = get_port(
        #         constants["spincoater"]["device_identifiers"]
        #     )  # find port to connect to this device.
        # else:
        #     self.port = port
        # self.ARDUINOTIMEOUT = constants["spincoater"]["pollingrate"]
        self.switch = switch
        self.COMMUNICATION_INTERVAL = constants["spincoater"]["communication_interval"]
        self.TIMEOUT = 30

        self.ACCELERATIONRANGE = (
            constants["spincoater"]["acceleration_min"],
            constants["spincoater"]["acceleration_max"],
        )  # rpm/s
        self.SPEEDRANGE = (
            constants["spincoater"]["rpm_min"],
            constants["spincoater"]["rpm_max"],
        )  # rpm
        self.__rpm = 0  # nominal current rpm. does not take ramping into account
        self.__HOMEPOSITION = 0.5  # home coordinate for spincoater chuck, in radial (0-1) coordinates. somewhat arbitrary, but avoid 0 because it wraps around to 1, makes some math annoying
        self.__TWISTDELTA = -0.05  # turn to make when twisting off sample from chuck.
        self._locked = False  # true when chuck is holding at home position
        self.gantry = gantry
        self.__calibrated = False
        # logging
        self.__logging_active = False
        self.__logdata = {"time": [], "rpm": []}
        self.LOGGINGINTERVAL = constants["spincoater"]["logging_interval"]

        self.VACUUM_DISENGAGEMENT_TIME = constants["spincoater"][
            "vacuum_disengagement_time"
        ]
        # give a little extra z clearance, crashing into the foil around the spincoater is annoying!
        self.p0 = np.asarray(constants["spincoater"]["p0"]) + [0, 0, 5]
        self.connect()
        self._current_rps = 0

    def connect(self, **kwargs):
        # connect to odrive BLDC controller
        print("Connecting to odrive")
        # this is admittedly hacky. Connect, reboot (which disonnects), then connect again. Reboot necessary when communication line is broken
        self.odrv0 = odrive.find_any()
        # try:
        #     self.odrv0 = odrive.find_any(timeout=10)
        # except:
        #     raise ValueError("Could not find odrive! confirm that 24V PSU is on")
        # try:
        #     self.odrv0.reboot()  # reboot the odrive, communication sometimes gets broken when we disconnect/reconnect
        #     self.odrv0._destroy()
        # except:
        #     pass  # this always throws an "object lost" error...which is what we want
        # try:
        #     self.odrv0 = odrive.find_any(timeout=10)
        # except:
        #     raise ValueError("Could not find odrive! confirm that 24V PSU is on")

        print("\tFound motor, now calibrating. This takes 10-20 seconds.")
        # input("\tPress enter once shroud is out of the way: ")
        self.axis = self.odrv0.axis0
        self.axis.requested_state = (
            AXIS_STATE_FULL_CALIBRATION_SEQUENCE  # calibrate the encoder
        )
        time.sleep(5)  # wait for calibration to initiate
        while self.axis.current_state != 1:
            time.sleep(1)  # wait for calibration to complete
        print("\tDone calibrating odrive!")
        self.axis.requested_state = (
            AXIS_STATE_CLOSED_LOOP_CONTROL  # normal control mode
        )
        # odrive defaults
        self.axis.motor.config.current_lim = 20  # Amps NOT SAME AS POWER SUPPLY CURRENT
        self.axis.controller.config.circular_setpoints = True  # position = 0-1 radial
        self.axis.trap_traj.config.vel_limit = (
            0.5  # for position moves to lock position
        )
        self.axis.trap_traj.config.accel_limit = 0.5
        self.axis.trap_traj.config.decel_limit = 0.5
        self.lock()
        self.idle()

        # start libfibre timer watchdog
        self.__connected = True
        self._libfibre_watchdog = threading.Thread(target=self.__libfibre_timer_worker)
        self._libfibre_watchdog.start()
        self._error_log = []

    def disconnect(self):
        self.__connected = False
        self._libfibre_watchdog.join()
        try:
            self.odrv0._destroy()
        except:
            pass  # this always throws an "object lost" error...which is what we want

    # position calibration methods
    def calibrate(self):
        """Prompt user to manually position the gantry over the spincoater using the Gantry GUI. This position will be recorded and used for future pick/place operations to the spincoater chuck"""
        # self.gantry.moveto(z=self.gantry.OT2_ZLIM, zhop=False)
        # self.gantry.moveto(x=self.gantry.OT2_XLIM, y=self.gantry.OT2_YLIM, zhop=False)
        # self.gantry.moveto(x=self.p0[0], y=self.p0[1], avoid_ot2=False, zhop=False)
        self.gantry.moveto(*self.p0)
        self.gantry.gui()
        self.coordinates = self.gantry.position
        # self.gantry.moverel(z=10, zhop=False)
        self.__calibrated = True
        with open(
            os.path.join(CALIBRATION_DIR, f"spincoater_calibration.yaml"), "w"
        ) as f:
            yaml.dump(self.coordinates, f)

    def _load_calibration(self):
        with open(
            os.path.join(CALIBRATION_DIR, f"spincoater_calibration.yaml"), "r"
        ) as f:
            self.coordinates = np.array(yaml.load(f, Loader=yaml.FullLoader))
        self.__calibrated = True

    def __call__(self):
        """Calling the spincoater object will return its gantry coordinates. For consistency with the callable nature of gridded hardware (storage, hotplate, etc)

        Raises:
                        Exception: If spincoater position is not calibrated, error will thrown.

        Returns:
                        tuple: (x,y,z) coordinates for gantry to pick/place sample on spincoater chuck.
        """
        if self.__calibrated == False:
            raise Exception(f"Need to calibrate spincoater position before use!")
        return self.coordinates

    # vacuum control methods

    def vacuum_on(self):
        """Turn on vacuum solenoid, pull vacuum"""
        self.switch.on()

    def vacuum_off(self):
        """Turn off vacuum solenoid, do not pull vacuum"""
        self.switch.off()

    # odrive BLDC motor control methods
    def set_rpm(self, rpm: int, acceleration: float = 1000):
        """sends commands to arduino to set a target speed with a target acceleration

        Args:
                        rpm (int): target angular velocity, in rpm
                        acceleration (float, optional): target angular acceleration, in rpm/second.  Defaults to 500.
        """
        rps = int(rpm / 60)  # convert rpm to rps for odrive
        acceleration = int(acceleration / 60)  # convert rpm/s to rps/s for odrive
        self.axis.controller.config.vel_ramp_rate = acceleration
        time.sleep(self.COMMUNICATION_INTERVAL)
        self.axis.controller.input_vel = rps
        time.sleep(self.COMMUNICATION_INTERVAL)

        # if acceleration == 0:
        #     acceleration = self.ACCELERATIONRANGE[1]  # default to max acceleration
        if self.axis.current_state != AXIS_STATE_CLOSED_LOOP_CONTROL:
            self.axis.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL

        self.axis.controller.config.control_mode = CONTROL_MODE_VELOCITY_CONTROL
        self.axis.controller.config.input_mode = INPUT_MODE_VEL_RAMP

        self._current_rps = rps
        self._locked = False

    def lock(self):
        """
        routine to lock rotor in registered position for sample transfer
        """
        if self._locked:
            return
        if self.axis.current_state != AXIS_STATE_CLOSED_LOOP_CONTROL:
            self.axis.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
        self.axis.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ
        # self.axis.controller.config.input_mode = INPUT_MODE_POS_FILTER
        self.axis.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
        time.sleep(self.COMMUNICATION_INTERVAL)
        self.axis.controller.input_pos = self.__HOMEPOSITION
        time.sleep(self.COMMUNICATION_INTERVAL)
        t0 = time.time()
        while (
            np.abs(self.__HOMEPOSITION - self.axis.encoder.pos_circular) > 0.05
        ):  # tolerance = 360*value degrees, 0.025 ~= 10 degrees
            time.sleep(0.1)
            if time.time() - t0 > self.TIMEOUT:
                print("resetting")
                self.reset()
                t0 = time.time()
        self._locked = True

    def reset(self):
        try:
            self.disconnect()
        except:
            pass
        self.connect()

    def twist_off(self):
        """
        routine to slightly rotate the chuck from home position.

        intended to help remove a stuck substrate from the o-ring, which can get sticky if
        perovskite solution drips onto the o-ring.
        """
        if not self._locked:
            raise Exception(
                "Cannot twist off the sample, the chuck is not currently locked!"
            )

        target_position = self.__HOMEPOSITION + self.__TWISTDELTA
        self.axis.controller.input_pos = target_position
        t0 = time.time()
        while (np.abs(target_position - self.axis.encoder.pos_circular)) > 0.025:
            time.sleep(0.1)
            if time.time() - t0 > self.TIMEOUT:
                print("resetting")
                self.reset()
                t0 = time.time()

    def stop(self):
        """
        stop rotation and locks the rotor in position
        """
        if self._locked:
            return
        self.set_rpm(0, 1000)
        t0 = time.time()
        min_stopped_time = 2
        while True:
            if self.axis.encoder.vel_estimate > 0:
                t0 = time.time()
            if time.time() - t0 > min_stopped_time:
                break
            time.sleep(0.1)
        self.lock()
        self.idle()

    def idle(self):
        if self.axis.current_state != AXIS_STATE_IDLE:
            self.axis.requested_state = AXIS_STATE_IDLE
        self._locked = False

    def _lookup_error(self):
        for err in dir(odrive.enums):
            if self.axis.error == getattr(odrive.enums, err):
                return err

    # logging code
    def __logging_worker(self):
        t0 = time.time()
        self.__logdata = {"time": [], "rpm": []}
        while self.__logging_active:
            self.__logdata["time"].append(time.time() - t0)
            self.__logdata["rpm"].append(
                self.axis.encoder.vel_estimate * 60
            )  # rps from odrive -> rpm
            time.sleep(self.LOGGINGINTERVAL)

    def start_logging(self):
        if self.__logging_active:
            raise ValueError("Logging is already active!")
        self.__logging_active = True
        self.__logging_thread = threading.Thread(target=self.__logging_worker)
        self.__logging_thread.start()

    def finish_logging(self):
        if not self.__logging_active:
            raise ValueError("Logging is already stopped!")
        self.__logging_active = False
        self.__logging_thread.join()
        return self.__logdata

    def __libfibre_timer_worker(self):
        """To prevent libfibre timers from accumulating, inducing global interpreter lock (GIL)


        Note:
        `odrv0._libfibre.timer_map` is a dictionary that adds a new `<TimerHandle>` entry once per second.
        As these entries accumulate, the terminal eventually slows down. I assume these are all involved
        in some background process within `libfibre` that accumulate into GIL. When i clear this dictionary
        by `odrv0._libfibre.timer_map = {}`, in a second or two (assuming this is the interval of the
        libfibre background process) the terminal speed goes back to normal. From what I can tell this does
        not affect operation of the odrive.

        We also clear errors to allow recovery if we're stuck
        """
        while self.__connected:
            time.sleep(1)
            if not self.__logging_active and len(self.odrv0._libfibre.timer_map) > 60:
                try:
                    latest_idx = max(list(self.odrv0._libfibre.timer_map.keys()))
                    self.odrv0._libfibre.timer_map = {
                        0: self.odrv0._libfibre.timer_map[latest_idx]
                    }

                    if self.axis.error > 0:
                        dt = datetime.strftime(datetime.now(), "%m/%d %H:%M:%S")
                        self._error_log.append((dt, self._lookup_error))
                        self.axis.clear_errors()
                except:
                    print(
                        "Spincoater unable to flush - probably disconnected, will try again later"
                    )

    def __del__(self):
        self.disconnect()
