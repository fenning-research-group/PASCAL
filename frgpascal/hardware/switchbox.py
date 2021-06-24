import numpy as np
import yaml
import os
import serial
from functools import partial
from .helpers import get_port


MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class Switchbox:
    """Interfaces with arduino to toggle relays for characterization hardware (relays, light sources, shutters, etc)"""

    def __init__(self, port=None):
        if port is None:
            self.port = get_port(constants["switchbox"]["device_identifiers"])
        else:
            self.port = port
        self.POLLINGDELAY = constants["switchbox"][
            "pollingrate"
        ]  # delay between sending a command and reading a response, in seconds

        self.__available_switches = [0, 1, 2, 3, 4, 5]
        self.connect()

    def connect(self):
        self._handle = serial.Serial(port=self.port, timeout=1, baudrate=115200)

    def __check_switch(self, switch):
        if switch not in self.available_switches:
            raise ValueError(f"Switch {switch} does not exist!")
        else:
            return True

    def set_low(self, switch: int):
        """sets a switch LOW

        Args:
            switch (int): index of switch to adjust
        """
        if self.__check_switch(switch):
            self._handle.write(f"L{switch}\n".encode())

    def set_high(self, switch: int):
        """sets a switch HIGH

        Args:
            switch (int): index of switch to adjust
        """
        if self.__check_switch(switch):
            self._handle.write(f"H{switch}\n".encode())

    def Switch(self, switch: int):
        """Returns a SingleSwitch object that controls single switch state

        Args:
            switch (int): index of switch to adjust
        """
        return SingleSwitch(switchid=switch, switchbox=self)


class SingleSwitch:
    """Exposes on/off control to a single switch"""

    def __init__(self, switchid, switchbox: Switchbox):
        self.switchid = switchid
        self.box = switchbox

    def on(self):
        self.switchbox.turn_on(self.switchid)

    def off(self):
        self.switchbox.turn_off(self.switchid)
