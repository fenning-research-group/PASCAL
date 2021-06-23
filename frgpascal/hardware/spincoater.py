import odrive  # odrive documentation https://docs.odriverobotics.com/
from odrive.enums import *  # control/state enumerations
import serial
import time
import numpy as np
import os
import yaml
import threading
from .helpers import get_port
from .gantry import Gantry

MODULE_DIR = os.path.dirname(__file__)
CALIBRATION_DIR = os.path.join(MODULE_DIR, "calibrations")
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.Loader)

# spincoater_serial_number = constants["spincoater"]["serialid"]
# print(constants["spincoater"])
p0 = constants["spincoater"]["p0"]


class SpinCoater:
    def __init__(
        self,
        gantry: Gantry,
        port=None,
        p0: tuple = p0,
    ):
        """Initialize the spincoater control object

        Args:
                                        gantry (Gantry): PASCAL Gantry control object
                                        serial_number (str, optional): Serial number for spincoater arduino, used to find and connect to correct COM port. Defaults to "558383339323513140D1":str.
                                        p0 (tuple, optional): Initial guess for gantry coordinates to drop sample on spincoater. Defaults to (52, 126, 36):tuple.
        """
        # constants
        if port is None:
            self.port = get_port(
                constants["spincoater"]["device_identifiers"]
            )  # find port to connect to this device.
        else:
            self.port = port
        self.ARDUINOTIMEOUT = constants["spincoater"]["pollingrate"]
        self.ACCELERATIONRANGE = (
            constants["spincoater"]["acceleration_min"],
            constants["spincoater"]["acceleration_max"],
        )  # rpm/s
        self.SPEEDRANGE = (
            constants["spincoater"]["rpm_min"],
            constants["spincoater"]["rpm_max"],
        )  # rpm
        self.__rpm = 0  # nominal current rpm. does not take ramping into account
        self.gantry = gantry
        self.__calibrated = False
        # logging
        self.__logging_active = False
        self.__logdata = {"time": [], "rpm": []}
        self.LOGGINGINTERVAL = constants["spincoater"]["logging_interval"]

        # give a little extra z clearance, crashing into the foil around the spincoater is annoying!
        self.p0 = np.asarray(p0) + [0, 0, 5]

    @property
    def rpm(self):
        return self.__rpm

    # @property.setter
    # def rpm(self, rpm: int):
    #     self.__rpm = rpm
    #     self.setrpm(rpm, self.ACCELERATIONRANGE[1])  # max acceleration

    def connect(self, **kwargs):
        # connect to odrive BLDC controller
        print("Connecting to odrive")
        try:
            self.odrv0 = odrive.find_any(timeout=10)
        except:
            raise ValueError("Could not find odrive! confirm that 24V PSU is on")
        print("Found motor, now calibrating. This takes 10-20 seconds.")
        self.axis = self.odrv0.axis0
        self.axis.requested_state = (
            AXIS_STATE_FULL_CALIBRATION_SEQUENCE  # calibrate the encoder
        )
        time.sleep(5)  # wait for calibration to initiate
        while self.axis.current_state != 1:
            time.sleep(1)  # wait for calibration to complete
        print("Done calibrating!")
        self.axis.requested_state = (
            AXIS_STATE_CLOSED_LOOP_CONTROL  # normal control mode
        )
        # odrive defaults
        self.axis.motor.config.current_lim = 60  # NOT SAME AS POWER SUPPLY CURRENT
        self.axis.controller.config.circular_setpoints = True  # position = 0-1 radial
        self.axis.trap_traj.config.vel_limit = 2  # for position moves to lock position
        self.axis.trap_traj.config.accel_limit = 1
        self.axis.trap_traj.config.decel_limit = 1

        # connect to arduino for vacuum relay control
        self.arduino = serial.Serial(port=self.port, timeout=1, baudrate=115200)

    def disconnect(self):
        self.arduino.close()
        try:
            self.odrv0.reboot()
            self.odrv0._destroy()
        except:
            pass  # this always throws an "object lost" error...which is what we want

    # position calibration methods
    def calibrate(self):
        """Prompt user to manually position the gantry over the spincoater using the Gantry GUI. This position will be recorded and used for future pick/place operations to the spincoater chuck"""
        self.gantry.open_gripper(
            12
        )  # TODO #7 dont hardcode the gripper opening position - maybe even keep it closed for this step?
        self.gantry.moveto(*self.p0)
        self.gantry.gui()
        self.coordinates = self.gantry.position
        self.gantry.moverel(z=10, zhop=False)
        self.gantry.close_gripper()
        self.__calibrated = True
        with open(
            os.path.join(CALIBRATION_DIR, f"spincoater_calibration.yaml"), "w"
        ) as f:
            yaml.dump(self.coordinates, f)

    def _load_calibration(self):
        with open(
            os.path.join(CALIBRATION_DIR, f"spincoater_calibration.yaml"), "r"
        ) as f:
            self.coordinates = yaml.load(f, Loader=yaml.FullLoader)
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

    # arduino/vacuum control methods
    def _wait_for_arduino(self):
        # TODO wait for arduino response
        t0 = time.time()
        while time.time() - t0 <= self.ARDUINOTIMEOUT:
            if self.arduino.in_waiting > 0:
                line = self.arduino.readline().decode("utf-8").strip()
                if line == "ok":
                    return
            time.sleep(0.2)
        return ValueError("No response from vacuum solenoid control arduino!")

    def vacuum_on(self):
        self.arduino.write(b"h")  # send command to engage/open vacuum solenoid
        self._wait_for_arduino()

    def vacuum_off(self):
        self.arduino.write(b"l\n")  # send command to engage/open vacuum solenoid
        self._wait_for_arduino()

    # odrive BLDC motor control methods
    def setrpm(self, rpm: int, acceleration: float = 500):
        """sends commands to arduino to set a target speed with a target acceleration

        Args:
                        rpm (int): target angular velocity, in rpm
                        acceleration (float, optional): target angular acceleration, in rpm/second.  Defaults to 500.
        """
        rps = int(rpm / 60)  # convert rpm to rps for odrive
        acceleration = int(acceleration / 60)  # convert rpm/s to rps/s for odrive
        # if acceleration == 0:
        #     acceleration = self.ACCELERATIONRANGE[1]  # default to max acceleration
        self.axis.controller.config.control_mode = CONTROL_MODE_VELOCITY_CONTROL
        self.axis.controller.config.input_mode = INPUT_MODE_VEL_RAMP
        self.axis.controller.config.vel_ramp_rate = acceleration
        self.axis.controller.input_vel = rps

    def lock(self):
        """
        routine to lock rotor in registered position for sample transfer
        """
        self.axis.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
        self.axis.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ
        self.axis.controller.input_pos = (
            0  # arbitrary, just needs to be same 0-1 position each time we "lock"
        )
        while self.axis.encoder.pos_circular > 0.001:  # tolerance = 0.36 degrees
            time.sleep(0.1)

    def stop(self):
        """
        stop rotation and locks the rotor in position
        """
        self.setrpm(0)
        # wait until the rotor is nearly stopped
        while self.axis.encoder.vel_estimate > 2:  # cutoff speed = two rotations/second
            time.sleep(0.1)
        self.lock()

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

    def __del__(self):
        self.disconnect()
