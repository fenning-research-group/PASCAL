import numpy as np
import yaml
import os
import serial
from functools import partial
from .helpers import get_port
import time

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["characterizationline"]


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
        self.RELAYRESPONSETIME = constants["switchbox"][
            "relayresponsetime"
        ]  # delay between changing relay state and relay open/closing
        self.__available_switches = [2, 3, 4, 5, 6, 7, 8, 9]
        self.connect()

    def connect(self):
        self._handle = serial.Serial(port=self.port, timeout=1, baudrate=115200)
        print("Connected to characterization switchbox")

    def __check_switch(self, switch):
        if switch not in self.__available_switches:
            raise ValueError(f"Switch {switch} does not exist!")
        else:
            return True

    def set_low(self, switch: int):
        """sets a switch LOW

        Args:
            switch (int): index of switch to adjust
        """
        if self.__check_switch(switch):
            self._handle.write(f"l{switch}\n".encode())
            time.sleep(self.RELAYRESPONSETIME)

    def set_high(self, switch: int):
        """sets a switch HIGH

        Args:
            switch (int): index of switch to adjust
        """
        if self.__check_switch(switch):
            self._handle.write(f"h{switch}\n".encode())
            time.sleep(self.RELAYRESPONSETIME)

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
        self.switchbox = switchbox

    def on(self):
        self.switchbox.set_high(self.switchid)

    def off(self):
        self.switchbox.set_low(self.switchid)
