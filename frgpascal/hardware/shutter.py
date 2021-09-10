import yaml
from frgpascal.hardware.helpers import get_port
import os
import serial
import time
from warnings import warn

# https://github.com/cdbaird/TL-rotation-control/blob/759dc3fc58efd975c37c7ee954fa6152618cd58e/elliptec/rotation.py

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["characterizationline"]["shutter"]


class Shutter:
    def __init__(self, port=None):
        # communication variables
        if port is None:
            self.port = get_port(constants["device_identifiers"])
        else:
            self.port = port
        self.POLLINGDELAY = constants[
            "pollingrate"
        ]  # delay (seconds) between sending a command and reading a response
        self.connect()

    def connect(self):
        self._handle = serial.Serial(self.port, timeout=5, baudrate=115200)

    def _wait_for_completion(self):
        t0 = time.time()
        while time.time() - t0 < 5:  # wait for 5 seconds
            if self._handle.in_waiting:
                out = self._handle.readline()
                if b"ok" in out:
                    return
            time.sleep(self.POLLINGDELAY)
        warn("Did not get a response from the transmission shutter!")

    def open(self):
        """open the shutter"""
        self._handle.write(b"u")  # up
        self._wait_for_completion()

    def close(self):
        """close the shutter"""
        self._handle.write(b"d")  # down
        self._wait_for_completion()
