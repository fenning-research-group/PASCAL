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
    """Interfaces with numato 16 relay board to toggle relays for
    characterization hardware (relays, light sources, shutters, etc)

    https://numato.com/product/16-channel-usb-relay-module/
    """

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
        self._relay_key = {
            0: "0",  # number in GB3: number of relay on numato board
            1: "1",
            2: "1",
            3: "1",
            4: "1",
            5: "1",
            6: "1",
            7: "1",
            8: "1",
            9: "1",
            10: "1",
            11: "1",
            12: "1",
            13: "1",
            14: "1",
        }
        self.connect()

    def connect(self):
        self._handle = serial.Serial(port=self.port, timeout=1)
        for relay in self._relay_key:
            self.set_low(relay)  # turn all relays off to start
        print("Connected to characterization switchbox")

    def _get_relay(self, switch):
        if switch not in self._relay_key:
            raise ValueError(f"Switch {switch} does not exist!")
        else:
            return self._relay_key[switch]

    def set_low(self, switch: int):
        """sets a switch LOW

        Args:
            switch (int): index of switch to adjust
        """
        relay = self._get_relay(switch)
        self._handle.write(f"relay off {relay}\n\r".encode())
        time.sleep(self.RELAYRESPONSETIME)

    def set_high(self, switch: int):
        """sets a switch HIGH

        Args:
            switch (int): index of switch to adjust
        """
        relay = self._get_relay(switch)
        self._handle.write(f"relay on {relay}\n\r".encode())
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
