import os
import yaml
import numpy as np
from abc import ABC, abstractmethod

MODULE_DIR = os.path.dirname(__file__)
with open(
    os.path.join(MODULE_DIR, "..", "hardware", "hardwareconstants.yaml"), "r"
) as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["characterizationline"]

invalid_keys = [
    "axis",
    "switchbox",
    "shutter",
    "filterslider",
]  # these are not characterization hardware
AVAILABLE_HARDWARE = [k for k in constants.keys() if k not in invalid_keys]


# individual characterization modes


class CharacterizationMethod(ABC):
    def __init__(self, name, hardware, jitter):
        if hardware not in AVAILABLE_HARDWARE:
            raise Exception(
                f"Invalid hardware: {hardware}. Choices are {AVAILABLE_HARDWARE}"
            )
        if np.abs(jitter) > 2.5:  # 2.5 mm offset from default position
            print(
                f"Warning- jitter of {jitter} mm is pretty high, your sample may not be characterized well!"
            )
        self.name = name
        self.hardware = hardware
        self.position = constants[hardware]["position"] + jitter

        if self.position < 0 or self.position > 400:
            raise Exception(
                f"Invalid position: {self.position}. Must be between 0 and 400. Check your jitter value!"
            )

    @abstractmethod
    def expected_duration(self) -> float:
        """calculate the expected time (seconds) to perform this task"""
        pass

    def to_dict(self):
        return {
            "name": self.name,
            "hardware": self.hardware,
            "position": self.position,
            "duration": self.expected_duration(),
            "details": self.details,
        }


class Darkfield(CharacterizationMethod):
    def __init__(self, dwelltimes=[0.05], jitter=0):
        for d in dwelltimes:
            if d <= 0 or d > 100:
                raise Exception(
                    f"Invalid dwelltime: {d} seconds. Must be 0<dwelltime<100 seconds"
                )
        self.dwelltimes = dwelltimes

        super().__init__(name="Darkfield", hardware="darkfield", jitter=jitter)

    def expected_duration(self):
        return sum([d for d in self.dwelltimes])  # convert to seconds

    def _get_details(self):
        return {
            "dwelltimes": [
                d * 1e6 for d in self.dwelltimes
            ],  # camera expect microseconds
        }


class Brightfield(CharacterizationMethod):
    def __init__(self):
        self.dwelltimes = [0.1]  # 100 ms static dwelltime

        super().__init__(name="Brightfield", hardware="brightfield", jitter=0)

    def expected_duration(self):
        return sum([d for d in self.dwelltimes])  # convert to seconds

    def _get_details(self):
        return {
            "dwelltimes": [
                d * 1e6 for d in self.dwelltimes
            ],  # camera expect microseconds
        }


class PLImaging(CharacterizationMethod):
    def __init__(self, dwelltimes=[0.05, 0.2, 1, 5], jitter: int = 0):
        for d in dwelltimes:
            if d <= 0 or d > 100:
                raise Exception(
                    f"Invalid dwelltime: {d} seconds. Must be 0<dwelltime<100 seconds"
                )
        self.dwelltimes = dwelltimes

        super().__init__(name="PLImaging", hardware="pl_imaging", jitter=jitter)

    def expected_duration(self):
        return sum([d for d in self.dwelltimes])  # seconds

    def _get_details(self):
        return {
            "dwelltimes": [
                d * 1e6 for d in self.dwelltimes
            ],  # camera expect microseconds
        }


class TransmissionSpectroscopy(CharacterizationMethod):
    def __init__(self, dwelltimes=[0.015, 0.05, 0.2, 1, 5, 15], numscans=2, jitter=0):
        for d in dwelltimes:
            if d <= 0 or d >= 60:
                raise Exception(
                    f"Invalid dwelltime: {d} seconds. Must be 0<dwelltime<60 seconds"
                )

        if numscans < 1 or numscans > 10:
            raise Exception(
                "numscans must be between 1 and 10 - user provided {numscans}"
            )
        self.dwelltimes = dwelltimes
        self.numscans = numscans

        super().__init__(
            name="TransmissionSpectroscopy",
            hardware="transmission",
            jitter=jitter,
        )

    def expected_duration(self):
        duration = sum(
            [d * self.numscans for d in self.dwelltimes]
        )  # seconds to take scans
        duration += (
            2 * constants["shutter"]["max_change_time"]
        )  # time to open/close the transmission shutter
        return duration

    def _get_details(self):
        return {
            "dwelltimes": [
                d * 1000 for d in self.dwelltimes
            ],  # spectrometer expects ms
            "numscans": self.numscans,
        }


class PLSpectroscopy(CharacterizationMethod):
    def __init__(self, dwelltimes=[0.1, 5, 20], numscans: int = 1, jitter: float = 0):
        for d in dwelltimes:
            if d <= 0 or d > 60:
                raise Exception(
                    f"Invalid dwelltime: {d} seconds. Must be 0<dwelltime<60 seconds"
                )

        if numscans < 1 or numscans > 10:
            raise Exception(
                "numscans must be between 1 and 10 - user provided {numscans}"
            )
        self.dwelltimes = dwelltimes
        self.numscans = numscans

        super().__init__(
            name="TransmissionSpectroscopy",
            hardware="pl_red",
            jitter=jitter,
        )

    def expected_duration(self):
        duration = sum(
            [d * self.numscans for d in self.dwelltimes]
        )  # seconds to take scans
        duration += (
            2 * constants["switchbox"]["relayresponsetime"]
        )  # relay trigger time for light on/off
        duration += constants["laser_settling_time"]  # settling time for laser

        return duration

    def _get_details(self):
        return {
            "dwelltimes": [
                d * 1000 for d in self.dwelltimes
            ],  # spectrometer expects ms
            "numscans": self.numscans,
        }


class PLPhotostability(CharacterizationMethod):
    def __init__(self, dwelltime: float = 2, duration: int = 120, jitter: float = 0):
        if dwelltime <= 0 or dwelltime > 60:
            raise Exception(
                f"Invalid dwelltime: {dwelltime} seconds. Must be 0<dwelltime<60 seconds"
            )
        self.dwelltime = dwelltime
        self.duration = duration

        super().__init__(
            name="PLPhotostability",
            hardware="pl_blue",
            jitter=jitter,
        )

    def expected_duration(self):
        duration = self.duration
        duration += (
            2 * constants["switchbox"]["relayresponsetime"]
        )  # relay trigger time for light on/off
        duration += constants["laser_settling_time"]  # settling time for laser

        return duration

    def _get_details(self):
        return {
            "dwelltimes": [
                d * 1000 for d in self.dwelltimes
            ],  # spectrometer expects ms
            "numscans": self.numscans,
        }
