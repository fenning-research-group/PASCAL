import odrive  # odrive documentation https://docs.odriverobotics.com/
from odrive.enums import *  # control/state enumerations
import serial
import time
import numpy as np
import os
import yaml
import threading
from abc import ABC, abstractmethod


MODULE_DIR = os.path.dirname(__file__)
CALIBRATION_DIR = os.path.join(MODULE_DIR, "calibrations")
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    print(f)
    constants = yaml.load(f, Loader=yaml.Loader)

# spincoater_serial_number = constants["spincoater"]["serialid"]
# print(constants["spincoater"])


class BaseSpinCoater(ABC):
    def __init__(self, gantry: Gantry, switch: SingleSwitch, sc_axis = 'axis0', regular_bootup = True):
         super().__init__()
        
    @abstractmethod
    def connect(self, **kwargs):
        raise NotImplementedError
    
    @abstractmethod
    def disconnect(self, reboot = False):
        raise NotImplementedError

    # position calibration methods
    @abstractmethod
    def calibrate(self):
        raise NotImplementedError

    @abstractmethod
    def _load_calibration(self):
        raise NotImplementedError

    @abstractmethod
    def __call__(self):
        raise NotImplementedError

    # vacuum control methods
    @abstractmethod
    def vacuum_on(self):
        """Turn on vacuum solenoid, pull vacuum"""
        raise NotImplementedError

    @abstractmethod
    def vacuum_off(self):
        """Turn off vacuum solenoid, do not pull vacuum"""
        raise NotImplementedError

    # odrive BLDC motor control methods
    @abstractmethod
    def set_rpm(self, rpm: int, acceleration: float = 1000):
        raise NotImplementedError

    @abstractmethod
    def lock(self):
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        raise NotImplementedError

    @abstractmethod
    def twist_off(self):
        """
        routine to slightly rotate the chuck from home position.

        intended to help remove a stuck substrate from the o-ring, which can get sticky if
        perovskite solution drips onto the o-ring.
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        """
        stop rotation and locks the rotor in position
        """
        raise NotImplementedError

    @abstractmethod
    def idle(self):
        raise NotImplementedError

    @abstractmethod
    def _lookup_error(self):
        raise NotImplementedError
    
    @abstractmethod
    # logging code
    def __logging_worker(self):
       raise NotImplementedError
    
    @abstractmethod
    def start_logging(self):
        raise NotImplementedError
    
    @abstractmethod
    def finish_logging(self):
        raise NotImplementedError
    
    @abstractmethod
    def __libfibre_timer_worker(self):
        """To prevent libfibre timers from accumulating, inducing global interpreter lock (GIL)


        Note:
        `odrv0._libfibre.timer_map` is a dictionary that adds a new `<TimerHandle>` entry once per second.
        As these entries accumulate, the terminal eventually slows down. I assume these are all involved
        in some background process within `libfibre` that accumulate into GIL. When i clear this dictionary
        by `odrv0._libfibre.timer_map = {}`, in a second or two (assuming this is the interval of the
        libfibre background process) the terminal speed goes back to normal. From what I can tell this does
        not affect operation of the odrive.

        We also clear errors to allow recovery if we're stuck
        """
        raise NotImplementedError

    def __del__(self):
        self.disconnect()
