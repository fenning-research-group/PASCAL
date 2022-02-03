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
    def __init__(
        self, exposure_time: float = 0.05, num_frames: int = 50, jitter: float = 0
    ):
        if exposure_time < 0.01 or exposure_time > 100:
            raise Exception(
                f"Invalid exposure time: {exposure_time} seconds. Must be 0.01<exposure_time<100 seconds"
            )
        if num_frames < 1 or num_frames > 500:
            raise Exception(
                "num_frames must be between 1 and 500 - user provided {num_frames}"
            )

        self.exposure_time = exposure_time
        self.num_frames = num_frames

        super().__init__(name="Darkfield", station="darkfield", jitter=jitter)

    def expected_duration(self):
        return self.exposure_time * self.num_frames

    def _get_details(self):
        return {"exposure_time": self.exposure_time, "num_frames": self.num_frames}


class Brightfield(CharacterizationTask):
    def __init__(self):
        self.exposure_time = 0.1  # 100 ms static dwelltime
        self.num_frames = 1

        super().__init__(name="Brightfield", station="brightfield", jitter=0)

    def expected_duration(self):
        return self.exposure_time

    def _get_details(self):
        return {"exposure_time": self.exposure_time, "num_frames": self.num_frames}


class PLImaging(CharacterizationTask):
    def __init__(
        self, exposure_times=[0.05, 0.2, 1, 5], num_frames: int = 1, jitter: int = 0
    ):
        for et in exposure_times:
            if et < 0.01 or et > 100:
                raise Exception(
                    f"Invalid exposure time: {et} seconds. Must be 0.01<dwelltime<100 seconds"
                )

        if num_frames < 1 or num_frames > 500:
            raise Exception(
                "num_frames must be between 1 and 500 - user provided {num_scans}"
            )
        self.exposure_times = exposure_times
        self.num_frames = num_frames

        super().__init__(name="PLImaging", station="pl_imaging", jitter=jitter)

    def expected_duration(self):
        return sum([d * self.num_frames for d in self.exposure_times])  # seconds

    def _get_details(self):
        return {"exposure_times": self.exposure_times, "num_frames": self.num_frames}


class TransmissionSpectroscopy(CharacterizationTask):
    def __init__(
        self, exposure_times=[0.02, 0.05, 0.2, 1, 5, 15], num_scans=2, jitter=0
    ):
        for et in exposure_times:
            if et < 0.02 or et > 60:
                raise Exception(
                    f"Invalid exposure time: {et} seconds. Must be 0.02<dwelltime<60 seconds"
                )

        if num_scans < 1 or num_scans > 10:
            raise Exception(
                "num_scans must be between 1 and 10 - user provided {num_scans}"
            )
        self.exposure_times = exposure_times
        self.num_scans = num_scans

        super().__init__(
            name="Transmission",
            station="transmission",
            jitter=jitter,
        )

    def expected_duration(self):
        duration = sum(
            [et * self.num_scans for et in self.exposure_times]
        )  # seconds to take scans
        duration += (
            2 * constants["shutter"]["max_change_time"]
        )  # time to open/close the transmission shutter
        return duration

    def _get_details(self):
        return {
            "exposure_times": self.exposure_times,
            "num_scans": self.num_scans,
        }


class PLSpectroscopy(CharacterizationTask):
    def __init__(
        self, exposure_times=[0.1, 5, 20], num_scans: int = 1, jitter: float = 0
    ):
        for et in exposure_times:
            if et < 0.02 or et > 60:
                raise Exception(
                    f"Invalid exposure time: {et} seconds. Must be 0.02<dwelltime<60 seconds"
                )

        if num_scans < 1 or num_scans > 10:
            raise Exception(
                "num_scans must be between 1 and 10 - user provided {num_scans}"
            )
        self.exposure_times = exposure_times
        self.num_scans = num_scans

        super().__init__(
            name="PL_635nm",
            station="pl_red",
            jitter=jitter,
        )

    def expected_duration(self):
        duration = sum(
            [et * self.num_scans for et in self.exposure_times]
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
            "exposure_times": self.exposure_times,
            "num_scans": self.num_scans,
        }


class PLPhotostability(CharacterizationTask):
    def __init__(
        self, exposure_time: float = 2, duration: int = 120, jitter: float = 0
    ):
        if exposure_time < 0.02 or exposure_time > 60:
            raise Exception(
                f"Invalid exposure time: {exposure_time} seconds. Must be 0.02<dwelltime<60 seconds"
            )
        self.exposure_time = exposure_time
        self.duration = duration
        self.num_measurements = ceil(duration / exposure_time)
        if self.num_measurements <= 5:
            print(
                "Warning: this photostability measurement (exposure time of {self.exposure_time} seconds for {self.duration} total seconds) will only have {self.num_measurements} timepoints!"
            )

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
            "exposure_time": self.exposure_time,
            "duration": self.duration,
            "num_measurements": self.num_measurements,
        }
