import numpy as np
import yaml
import os
import serial
from functools import partial
from .helpers import get_port
import time
from threading import Lock

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
            1: "1",
            2: "2",
            3: "3",
            4: "C",
            5: "D",
            6: "E",
            7: "F",
            8: "0",
            9: "4",
            10: "5",
            11: "6",
            12: "9",
            13: "A",
            14: "B",
            "vacuumsolenoid": "8",  # relay 8 and 9 are not being used for switchboard
            "unused": "9",
        }
        self._lock = (
            Lock()
        )  # to prevent multiple workers from talking to switchbox simultaneously
        self.connect()

    def connect(self):
        self._handle = serial.Serial(port=self.port, timeout=5)
        print("Connected to characterization switchbox")

    def _get_relay(self, switch):
        if switch not in self._relay_key:
            raise ValueError(f"Switch {switch} does not exist!")
        else:
            return self._relay_key[switch]

    def off(self, switch: int):
        """sets a switch LOW

        Args:
            switch (int): index of switch to adjust
        """
        relay = self._get_relay(switch)
        with self._lock:
            self._handle.write(f"relay off {relay}\n\r".encode())
        time.sleep(self.RELAYRESPONSETIME)

    def on(self, switch: int):
        """sets a switch HIGH

        Args:
            switch (int): index of switch to adjust
        """
        relay = self._get_relay(switch)
        with self._lock:
            self._handle.write(f"relay on {relay}\n\r".encode())
        time.sleep(self.RELAYRESPONSETIME)

    def all_off(self):
        """
        sets all relays low
        """
        for relay in self._relay_key:
            self.off(relay)  # turn all relays off to start

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
        self.switchbox.on(self.switchid)

    def off(self):
        self.switchbox.off(self.switchid)
