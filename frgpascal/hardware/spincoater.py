import serial
import time
import numpy as np
import pickle
import os
import yaml
from datetime import datetime
from .helpers import get_port
from .gantry import Gantry

MODULE_DIR = os.path.dirname(__file__)
constants = yaml.load(
    os.path.join(MODULE_DIR, "hardwareconstants.yaml"), Loader=yaml.Loader
)
spincoater_serial_number = constants["spincoater"]["serialid"]
p0 = constants["spincoater"]["p0"]


class SpinCoater:
    def __init__(
        self,
        gantry: Gantry,
        p0: tuple = p0,
    ):
        """Initialize the spincoater control object

        Args:
                                        gantry (Gantry): PASCAL Gantry control object
                                        serial_number (str, optional): Serial number for spincoater arduino, used to find and connect to correct COM port. Defaults to "558383339323513140D1":str.
                                        p0 (tuple, optional): Initial guess for gantry coordinates to drop sample on spincoater. Defaults to (52, 126, 36):tuple.
        """
        # constants
        self.port = get_port(constants['spincoater'])  # find port to connect to this device.
        self.POLLINGRATE = constants["spincoater"][
            "pollingrate"
        ]  # query rate to arduino, in seconds
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
        self.locked = None
        self.connect()
        self.unlock()
        self.__calibrated = False

        # logging
        self.__logging_active = False

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
        self.__handle = serial.Serial(
            port=self.port, baudrate=57600, timeout=2, write_timeout=2, **kwargs
        )

    def disconnect(self):
        self.__handle.close()

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
            "spincoater_calibration.pkl", "wb"
        ) as f:  # TODO #6 save the calibration files as yaml, not pickle
            pickle.dump(self.coordinates, f)

    def _load_calibration(self):
        with open("spincoater_calibration.pkl", "rb") as f:  # TODO #6
            self.coordinates = pickle.load(f)
        self.__calibrated = True

    def write(self, s):
        """
        appends terminator and converts to bytes before sending message to arduino
        """
        self.__handle.write(f"{s}\n".encode())

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

    def vacuum_on(self):
        self.write("v1")  # send command to engage/open vacuum solenoid

    def vacuum_off(self):
        self.write("v0")  # send command to disengage/close vacuum solenoid

    def lock(self):
        """
        routine to lock rotor in registered position for sample transfer
        """
        if not self.locked:
            self.write("c1")  # send command to engage electromagnet
            self.locked = True

    def unlock(self):
        """
        unlocks the rotor from registered position to allow spinning again
        """
        if self.locked:
            self.write("c0")  # send command to disengage electromagnet
            # time.sleep(2) #wait some time to ensure rotor has unlocked before attempting to rotate
            self.locked = False

    def setrpm(self, rpm: int, acceleration: float = 0):
        """sends commands to arduino to set a target speed with a target acceleration

        Args:
                        rpm (int): target angular velocity, in rpm
                        acceleration (float, optional): target angular acceleration, in rpm/second.  Defaults to 500.
        """
        rpm = int(rpm)  # arduino only takes integer inputs
        if acceleration == 0:
            acceleration = self.ACCELERATIONRANGE[1]  # default to max acceleration
        duration = abs(
            (rpm - self.__rpm) / acceleration
        )  # time (s) to move from current rpm to target rpm at this acceleration rate
        duration = int(
            duration * 1000
        )  # round time to nearest milliseconds for arduino

        self.unlock()  # confirm that the chuck electromagnet is disengaged
        self.__handle.write(
            f"a{rpm:d} {duration:d}"
        )  # send command to arduino. assumes arduino responds to "s{rpm},{acceleration}\r'

        self.__rpm = rpm

    def stop(self):
        """
        stop rotation and locks the rotor in position
        """
        self.setrpm(0)  #
        time.sleep(
            2
        )  # wait some time to ensure rotor has stopped and engaged with electromagnet
        self.lock()
        time.sleep(1)

    def logging_on(self):
        if self.__logging_active:
            raise ValueError("Logging is already active!")
        self.write("l1")
        self.__logging_active = True

    def logging_off(self):
        if not self.__logging_active:
            raise ValueError("Logging is already stopped!")
        self.write("l0")
        self.__logging_active = False

    def logging_retrieve(self):
        """Reads the logged rpm vs time from spincoater SD card

        Raises:
            ValueError: spincoater must not be actively logging to retrieve data

        Returns:
            data: dictionary with datetime, seconds (relative time), rpm, and rpm_target fields.
        """
        if self.__logging_active:
            raise ValueError(
                "Logging is currently active - stope with .logging_off() before retrieving data."
            )
        self.write("d")
        time.sleep(0.5)  # let arduino parse and start writing data to serial
        datetime = []
        rpm_nominal = []
        rpm_actual = []
        while self.__handle.in_waiting:
            line = self.__handle.readline().decode("utf-8").split(",")
            datetime.append(datetime.strptime(line[0], "%Y/%m/%d %H:%M:%S"))
            rpm_nominal.append(float(line[1]))
            rpm_actual.append(float(line[2]))
            # time.sleep(self.POLLINGRATE)
        datetime = np.array(datetime)
        rpm_nominal = np.array(rpm_nominal)
        rpm_actual = np.array(rpm_actual)
        relativetime = [t.total_seconds() for t in datetime - datetime[0]]  # seconds

        data = {
            "datetime": datetime,
            "seconds": relativetime,
            "rpm_target": rpm_nominal,
            "rpm": rpm_actual,
        }
        return data
