import yaml
from frgpascal.hardware.helpers import get_port
import os
import serial
import time

# https://github.com/cdbaird/TL-rotation-control/blob/759dc3fc58efd975c37c7ee954fa6152618cd58e/elliptec/rotation.py

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["characterizationline"][
        "filterslider"
    ]


class FilterSlider:
    def __init__(self, port=None):
        # communication variables
        if port is None:
            self.port = get_port(constants["device_identifiers"])
        else:
            self.port = port
        self.POLLINGDELAY = constants[
            "pollingrate"
        ]  # delay (seconds) between sending a command and reading a response
        self.SHUTTERRESPONSETIME = constants[
            "shutterresponsetime"
        ]  # delay (seconds) between telling shutter to move -> shutter completing the move
        self.ADDRESS_TOP = constants["top"]
        self.ADDRESS_BOTTOM = constants["bottom"]

        self.connect()

    def connect(self):
        self._handle = serial.Serial(self.port, timeout=3, baudrate=9600)

    def write(self, address, request):
        command = address.encode("utf-8") + request.encode("utf-8")
        self._handle.write(command)
        response = self._handle.readline().decode("utf-8")
        # if (len(response) == 0) or (response[0] != address):
        #     raise ValueError("Shutter did not complete move!")

    # def gohome(self):
    #     """homes the motor"""
    #     self.write("i2")
    #     response = self.read_until(terminator=b"\n")

    def top_left(self):
        """Move top shutter to left position"""
        self.write(address=self.ADDRESS_TOP, request="fw")
        time.sleep(self.SHUTTERRESPONSETIME)

    def top_right(self):
        """Move top shutter to right position"""
        self.write(address=self.ADDRESS_TOP, request="bw")
        time.sleep(self.SHUTTERRESPONSETIME)

    def bottom_left(self):
        """Move bottom shutter to left position"""
        self.write(address=self.ADDRESS_BOTTOM, request="bw")
        time.sleep(self.SHUTTERRESPONSETIME)

    def bottom_right(self):
        """Move bottom shutter to right position"""
        self.write(address=self.ADDRESS_BOTTOM, request="fw")
        time.sleep(self.SHUTTERRESPONSETIME)
