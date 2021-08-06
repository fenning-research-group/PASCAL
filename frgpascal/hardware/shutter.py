import yaml
from frgpascal.hardware.helpers import get_port
import os
import serial

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
        ]  # delay between sending a command and reading a response, in seconds

    def connect(self):
        self._handle = serial.Serial(self.port, timeout=1, baudrate=9600)

    def write(self, request, data=None, address="0"):
        command = address.encode("utf-8") + request.encode("utf-8")
        if data is not None:
            command += data.encode("utf-8")
        self._handle.write(command)

    def gohome(self):
        """homes the motor"""
        self.write("i2")
        response = self.read_until(terminator=b"\n")

    def left(self):
        """
        Move shutter to left position
        """
        self.write("f1")

    def right(self):
        """
        Move shutter to right position
        """
        self.write("b1")
