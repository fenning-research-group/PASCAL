# from termios import error
import time
import numpy as np
import yaml
from frgpascal.hardware.helpers import get_port
import os
import serial
import threading

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class Gripper:
    # gripper variables
    def __init__(self, port=None):
        # communication variables
        if port is None:
            self.port = get_port(constants["gripper"]["device_identifiers"])
        else:
            self.port = port
        self.POLLINGDELAY = constants["gripper"][
            "pollingrate"
        ]  # delay between sending a command and reading a response, in seconds

        self.__gripperwatchdogthread = threading.Thread(
            target=self.__watch_gripper_timeout, daemon=True
        )
        self.__stop_gripperidlethread = False
        self.__gripper_last_opened = np.inf
        self.GRIPPERTIMEOUT = constants["gripper"][
            "idle_timeout"
        ]  # gripper will automatically close if left open for this long (s)
        self.LOADTHRESHOLD = constants["gripper"][
            "springs_loaded_threshold"
        ]  # value above which gripper considered under load from springs

        self.MAXPWM = constants["gripper"]["pwm_max"]  # max pwm signal (us)
        self.MINPWM = constants["gripper"]["pwm_min"]
        self.MAXWIDTH = constants["gripper"]["width_max"]  # max gripper width, in mm
        self.MINWIDTH = constants["gripper"]["width_min"]
        self.SLOWGRIPPERINTERVAL = constants["gripper"]["slow_interval"]
        self.FASTGRIPPERINTERVAL = constants["gripper"]["fast_interval"]

        self.currentwidth = self.MINWIDTH
        self.currentpwm = self.MINPWM
        self.connect()  # connect to gripper by default
        self.close()  # close gripper by default
        # self.write(f"S{self.MINPWM} {self.SLOWGRIPPERINTERVAL}")

    def connect(self):
        self._handle = serial.Serial(port=self.port, timeout=1, baudrate=115200)
        time.sleep(3)  # takes a few seconds for connection to establish
        self.__start_gripper_timeout_watchdog()

    def disconnect(self):
        self._handle.close()
        del self._handle

    def write(self, msg):
        self._handle.write(f"{msg}\n".encode())
        time.sleep(self.POLLINGDELAY)

    def _waitformovement(self):
        # return
        readline = ""
        time0 = time.time()
        while readline != "done":
            if time.time() - time0 > 2:  # self.GRIPPERTIMEOUT:
                raise ValueError("Gripper timed out during movement")
            if self._handle.in_waiting > 0:
                readline = self._handle.readline().decode("utf-8").strip()
            time.sleep(self.POLLINGDELAY)

    # gripper methods
    def open(self, width=None, slow=False):
        """
        open gripper to width, in mm
        """
        if width is None:
            width = self.MAXWIDTH

        pwm = self.__width_to_pwm(width)
        if slow:
            rate = self.SLOWGRIPPERINTERVAL
        else:
            rate = self.FASTGRIPPERINTERVAL
        self.write(f"S{pwm} {rate}")
        self._waitformovement()
        self.__gripper_last_opened = time.time()
        self.currentwidth = width
        self.currentpwm = pwm

    def close(self, slow=False):
        """
        close the gripper to minimum width
        """
        self.open(width=self.MINWIDTH, slow=slow)

    def is_under_load(self):
        self.write("l")
        time.sleep(self.POLLINGDELAY)
        load = float(self._handle.readline())
        if load > self.LOADTHRESHOLD:
            return True
        else:
            return False

    def __pwm_to_width(self, angle):
        """
        convert servo pwm (pulse width us) to gripper opening width (mm)
        """
        if (angle > self.MAXPWM) or (angle < self.MINPWM):
            raise Exception(
                f"Angle {angle} outside acceptable range ({self.MINPWM}-{self.MAXPWM})"
            )

        fractional_angle = (angle - self.MINPWM) / (self.MAXPWM - self.MINPWM)
        width = fractional_angle * (self.MAXWIDTH - self.MINWIDTH) + self.MINWIDTH

        return np.round(width, 1)

    def __width_to_pwm(self, width):
        """
        convert gripper width (mm) to servo pulse width (us)
        """
        if (width > self.MAXWIDTH) or (width < self.MINWIDTH):
            raise Exception(
                f"Width {width} outside acceptable range ({self.MINWIDTH}-{self.MAXWIDTH})"
            )

        fractional_width = (width - self.MINWIDTH) / (self.MAXWIDTH - self.MINWIDTH)
        angle = fractional_width * (self.MAXPWM - self.MINPWM) + self.MINPWM

        return np.round(angle, 0).astype(int)  # nearest angle

    # gripper timeout watchdog
    def __start_gripper_timeout_watchdog(self):
        self.__stop_gripperidlethread = False
        if not self.__gripperwatchdogthread.is_alive():
            self._gripperwatchdogthread = threading.Thread(
                target=self.__watch_gripper_timeout, daemon=True
            )
            self._gripperwatchdogthread.start()

    def __stop_gripper_timeout_watchdog(self):
        self.__stop_gripperidlethread = True
        print("Waiting for gripper timeout watchdog thread to finish up...")
        while self.__gripperwatchdogthread.is_alive():
            time.sleep(1)
            print(".")

    def __watch_gripper_timeout(self):
        interval = self.GRIPPERTIMEOUT / 10
        while True:
            time.sleep(interval)
            if self.__stop_gripperidlethread:
                break
            if self.currentpwm == self.MINPWM:
                continue
            if time.time() - self.__gripper_last_opened >= self.GRIPPERTIMEOUT:
                self.close()