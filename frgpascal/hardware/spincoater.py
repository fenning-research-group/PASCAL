import serial
import time
import numpy as np
import pickle
import os
import yaml
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
        serial_number: str = spincoater_serial_number,
        p0: tuple = p0,
    ):
        """Initialize the spincoater control object

        Args:
                                        gantry (Gantry): PASCAL Gantry control object
                                        serial_number (str, optional): Serial number for spincoater arduino, used to find and connect to correct COM port. Defaults to "558383339323513140D1":str.
                                        p0 (tuple, optional): Initial guess for gantry coordinates to drop sample on spincoater. Defaults to (52, 126, 36):tuple.
        """
        # constants
        self.port = get_port(serial_number)  # find port to connect to this device.
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
        self.gantry = gantry
        self.locked = None
        self.connect()
        self.unlock()
        self.__calibrated = False

        # give a little extra z clearance, crashing into the foil around the spincoater is annoying!
        self.p0 = np.asarray(p0) + [0, 0, 5]

    def connect(self, **kwargs):
        self.__handle = serial.Serial(
            port=self.port, baudrate=57600, timeout=2, write_timeout=2, **kwargs
        )

    def disconnect(self):
        self.__handle.close()

    def calibrate(self):
        """Prompt user to manually position the gantry over the spincoater using the Gantry GUI. This position will be recorded and used for future pick/place operations to the spincoater chuck"""
        self.gantry.open_gripper(12)
        self.gantry.moveto(*self.p0)
        self.gantry.gui()
        self.coordinates = self.gantry.position
        self.gantry.moverel(z=10, zhop=False)
        self.gantry.close_gripper()
        self.__calibrated = True
        with open("spincoater_calibration.pkl", "wb") as f:
            pickle.dump(self.coordinates, f)

    def _load_calibration(self):
        with open("spincoater_calibration.pkl", "rb") as f:
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

    @property
    def rpm(self):
        self.write("c")  # command to read rpm
        self.__rpm = float(self.__handle.readline().strip())
        return self.__rpm

    @rpm.setter
    def rpm(self, rpm):
        if rpm == 0:
            self.stop()
        else:
            self.setspeed(rpm)

    def vacuum_on(self):
        self.write("i3")  # send command to engage/open vacuum solenoid

    def vacuum_off(self):
        self.write("o3")  # send command to disengage/close vacuum solenoid

    def lock(self):
        """
        routine to lock rotor in registered position for sample transfer
        """
        if not self.locked:
            self.write("i4")  # send command to engage electromagnet
            self.locked = True

    def unlock(self):
        """
        unlocks the rotor from registered position to allow spinning again
        """
        if self.locked:
            self.write("o4")  # send command to disengage electromagnet
            # time.sleep(2) #wait some time to ensure rotor has unlocked before attempting to rotate
            self.locked = False

    def setspeed(self, speed: float, acceleration: float = 500):
        """sends commands to arduino to set a target speed with a target acceleration

        Args:
                        speed (float): target angular velocity, in rpm
                        acceleration (float, optional): target angular acceleration, in rpm/second.  Defaults to 500.
        """
        speed = int(speed)  # arduino only takes integer inputs

        self.unlock()
        self.__handle.write(f"a{speed:d}".encode())
        # send command to arduino. assumes arduino responds to "s{rpm},{acceleration}\r'

    def stop(self):
        """
        stop rotation and locks the rotor in position
        """
        self.write("z")  #
        time.sleep(
            2
        )  # wait some time to ensure rotor has stopped and engaged with electromagnet
        self.lock()
        time.sleep(1)

    def recipe(self, recipe):  ### TODO

        record = {"time": [], "rpm": []}

        start_time = round(time.time())  # big ass number
        next_step_time = 0
        time_elapsed = 0
        # first step == true
        for step in recipe:
            speed = step[0]
            duration = step[1]

            # if first_step == true:

            # 	first_step == false
            # self.write('d')
            self.setspeed(speed)
            next_step_time += duration

            while time_elapsed <= next_step_time:
                time_elapsed = time.time() - start_time
                record["rpm"].append(self.rpm)
                record["time"].append(time_elapsed)
                time.sleep(self.POLLINGRATE)

            # self.write('f')
        self.lock()

        return record
