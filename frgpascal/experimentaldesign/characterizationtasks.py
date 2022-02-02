import os
import yaml
import numpy as np
from abc import ABC, abstractmethod
from math import ceil

MODULE_DIR = os.path.dirname(__file__)
with open(
    os.path.join(MODULE_DIR, "..", "hardware", "hardwareconstants.yaml"), "r"
) as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["characterizationline"]

AVAILABLE_STATION = [k for k in constants["stations"].keys()]


# individual characterization modes


class CharacterizationTask(ABC):
    def __init__(self, name, station, jitter):
        if station not in AVAILABLE_STATION:
            raise Exception(
                f"Invalid station: {station}. Choices are {AVAILABLE_STATION}"
            )
        if np.abs(jitter) > 2:  # 2 mm offset from default position
            print(
                f"Warning- jitter of {jitter} mm is pretty high, your sample may not be positioned properly for characterization!"
            )
        self.name = name
        self.station = station
        self.position = constants["stations"][station]["position"] + jitter

        if (
            self.position < constants["axis"]["x_min"]
            or self.position > constants["axis"]["x_max"]
        ):
            raise Exception(
                f"Invalid position: {self.position}. Must be between 0 and 400. Check your jitter value!"
            )

    @abstractmethod
    def expected_duration(self) -> float:
        """calculate the expected time (seconds) to perform this task"""
        pass

    @abstractmethod
    def _get_details(self) -> dict:
        """generates dictionary of details for specific characterization task"""
        return {}

    def to_dict(self):
        return {
            "name": self.name,
            "station": self.station,
            "position": self.position,
            "duration": self.expected_duration(),
            "details": self._get_details(),
        }


class Darkfield(CharacterizationTask):
    def __init__(self, dwelltimes=[0.05], numframes=100, jitter=0):
        for d in dwelltimes:
            if d < 0.01 or d > 100:
                raise Exception(
                    f"Invalid dwelltime: {d} seconds. Must be 0.01<dwelltime<100 seconds"
                )
        if numframes < 1 or numframes > 500:
            raise Exception(
                "numscans must be between 1 and 500 - user provided {numscans}"
            )

        self.dwelltimes = dwelltimes
        self.numframes = numframes

        super().__init__(name="Darkfield", station="darkfield", jitter=jitter)

    def expected_duration(self):
        return sum([d * self.numframes for d in self.dwelltimes])  # convert to seconds

    def _get_details(self):
        return {"dwelltimes": self.dwelltimes, "numframes": self.numframes}


class Brightfield(CharacterizationTask):
    def __init__(self):
        self.dwelltimes = [0.1]  # 100 ms static dwelltime
        self.numframes = 1

        super().__init__(name="Brightfield", station="brightfield", jitter=0)

    def expected_duration(self):
        return sum([d * self.numframes for d in self.dwelltimes])  # convert to seconds

    def _get_details(self):
        return {"dwelltimes": self.dwelltimes, "numframes": self.numframes}


class PLImaging(CharacterizationTask):
    def __init__(
        self, dwelltimes=[0.05, 0.2, 1, 5], numframes: int = 1, jitter: int = 0
    ):
        for d in dwelltimes:
            if d < 0.01 or d > 100:
                raise Exception(
                    f"Invalid dwelltime: {d} seconds. Must be 0.01<dwelltime<100 seconds"
                )

        if numframes < 1 or numframes > 500:
            raise Exception(
                "numscans must be between 1 and 500 - user provided {numscans}"
            )
        self.dwelltimes = dwelltimes
        self.numframes = numframes

        super().__init__(name="PLImaging", station="pl_imaging", jitter=jitter)

    def expected_duration(self):
        return sum([d * self.numframes for d in self.dwelltimes])  # seconds

    def _get_details(self):
        return {"dwelltimes": self.dwelltimes, "numframes": self.numframes}


class TransmissionSpectroscopy(CharacterizationTask):
    def __init__(self, dwelltimes=[0.02, 0.05, 0.2, 1, 5, 15], numscans=2, jitter=0):
        for d in dwelltimes:
            if d < 0.02 or d > 60:
                raise Exception(
                    f"Invalid dwelltime: {d} seconds. Must be 0.02<dwelltime<60 seconds"
                )

        if numscans < 1 or numscans > 10:
            raise Exception(
                "numscans must be between 1 and 10 - user provided {numscans}"
            )
        self.dwelltimes = dwelltimes
        self.numscans = numscans

        super().__init__(
            name="Transmission",
            station="transmission",
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
            "dwelltimes": self.dwelltimes,
            "numscans": self.numscans,
        }


class PLSpectroscopy(CharacterizationTask):
    def __init__(self, dwelltimes=[0.1, 5, 20], numscans: int = 1, jitter: float = 0):
        for d in dwelltimes:
            if d < 0.02 or d > 60:
                raise Exception(
                    f"Invalid dwelltime: {d} seconds. Must be 0.02<dwelltime<60 seconds"
                )

        if numscans < 1 or numscans > 10:
            raise Exception(
                "numscans must be between 1 and 10 - user provided {numscans}"
            )
        self.dwelltimes = dwelltimes
        self.numscans = numscans

        super().__init__(
            name="PL_635nm",
            station="pl_red",
            jitter=jitter,
        )

    def expected_duration(self):
        duration = sum(
            [d * self.numscans for d in self.dwelltimes]
        )  # seconds to take scans
        duration += (
            2 * constants["switchbox"]["relayresponsetime"]
        )  # relay trigger time for light on/off
        duration += constants["stations"]["pl_red"][
            "laser_settling_time"
        ]  # settling time for laser

        return duration

    def _get_details(self):
        return {
            "dwelltimes": self.dwelltimes,
            "numscans": self.numscans,
        }


class PLPhotostability(CharacterizationTask):
    def __init__(self, dwelltime: float = 2, duration: int = 120, jitter: float = 0):
        if dwelltime < 0.02 or dwelltime > 60:
            raise Exception(
                f"Invalid dwelltime: {dwelltime} seconds. Must be 0.02<dwelltime<60 seconds"
            )
        self.dwelltime = dwelltime
        self.duration = duration
        self.numscans = ceil(duration / dwelltime)

        super().__init__(
            name="Photostability_405nm",
            station="pl_blue",
            jitter=jitter,
        )

    def expected_duration(self):
        duration = self.duration
        duration += (
            2 * constants["switchbox"]["relayresponsetime"]
        )  # relay trigger time for light on/off
        duration += constants["stations"]["pl_red"][
            "laser_settling_time"
        ]  # settling time for laser

        return duration

    def _get_details(self):
        return {
            "dwelltime": self.dwelltime,
            "numscans": self.numscans,
        }
