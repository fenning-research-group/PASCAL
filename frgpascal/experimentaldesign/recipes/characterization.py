import numpy as np

AVAILABLE_STATIONS = ["darkfield_camera", "brightfield_camera", "spectroscopy"]

AVAILABLE_LASERS = [405, 635]


class CharacterizationStationTemplate:
    def __init__(self, station):
        if station not in AVAILABLE_STATIONS:
            raise ValueError(
                f"Station does not exist! available options are {AVAILABLE_STATIONS}"
            )
        self.station = station


class DarkfieldImage(CharacterizationStationTemplate):
    """
    takes single or list of dwell times (ms)
    """

    def __init__(self, dwell=[50]):
        super().__init__(station="darkfield_camera")
        if type(dwell) is not list or np.array:
            dwell = list(dwell)
        self.dwell = dwell


class PLImage(CharacterizationStationTemplate):
    """
    takes single or list of dwell times (ms)
    """

    def __init__(self, dwell=[50, 200, 1000]):
        super().__init__(station="darkfield_camera")
        if type(dwell) is not list or np.array:
            dwell = list(dwell)
        self.dwell = dwell


class BrightfieldImage(CharacterizationStationTemplate):
    """
    takes single or list of dwell times (ms)
    """

    def __init__(self, dwell=[50]):
        super().__init__(station="brightfield_camera")
        if type(dwell) is not list or np.array:
            dwell = list(dwell)
        self.dwell = dwell


class PLSpectroscopy(CharacterizationStationTemplate):
    """
    takes single or list of dwell times (ms)
    """

    def __init__(self, laser, dwell):
        if laser not in AVAILABLE_LASERS:
            raise ValueError(
                f"Laser does not exist! available options are {AVAILABLE_LASERS}"
            )
        self.laser = laser
        super().__init__(station="specroscopy")
        if type(dwell) is not list or np.array:
            dwell = list(dwell)
        self.dwell = dwell


class TransmissionSpectroscopy(CharacterizationStationTemplate):
    """
    takes single or list of dwell times (ms)
    """

    def __init__(self, laser, dwell):
        if laser not in AVAILABLE_LASERS:
            raise ValueError(
                f"Laser does not exist! available options are {AVAILABLE_LASERS}"
            )
        self.laser = laser
        super().__init__(station="specroscopy")
        if type(dwell) is not list or np.array:
            dwell = list(dwell)
        self.dwell = dwell
