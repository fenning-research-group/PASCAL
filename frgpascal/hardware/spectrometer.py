import sys
import os

sys.path.append(os.path.dirname(__file__))

import numpy as np
import stellarnet_driver3 as sn  # usb driver
from scipy.optimize import minimize


class Spectrometer:
    """Object to interface with Stellarnet spectrometer"""

    def __init__(self, address=0):
        self.id, self.__wl = sn.array_get_spec(address)
        self._baseline_light = None
        self._baseline_dark = None
        self._hdr_times = [
            100,
            250,
            500,
            2000,
            15000,
        ]  # duration times (ms) for high dynamic range measurements
        print("Connected to spectrometer")
        self.integrationtime = self._hdr_times[0]  # ms
        self.numscans = 1  # one scan per spectrum
        self.smooth = 0  # smoothing factor, units unclear

    @property
    def integrationtime(self):
        return self.__integrationtime

    @integrationtime.setter
    def integrationtime(self, t):
        self.id["device"].set_config(int_time=t)
        self.__integrationtime = t

    @property
    def numscans(self):
        return self.__numscans

    @numscans.setter
    def numscans(self, n):
        self.id["device"].set_config(scans_to_avg=n)
        self.__numscans = n

    @property
    def smooth(self):
        return self.__smooth

    @smooth.setter
    def smooth(self, n):
        self.id["device"].set_config(x_smooth=n)
        self.__smooth = n

    def capture(self):
        """
        captures a spectrum from the usb spectrometer
        """
        spectrum = sn.array_spectrum(self.id, self.__wl)
        spectrum[:, 1] /= self.integrationtime  # convert to counts per second
        return spectrum

    def capture_hdr(self):
        """captures an HDR spectrum
        """
        threshold = 2 ** 16 * 0.95  # counts above this are considered saturated

        for i, t in enumerate(self._hdr_times):
            self.integrationtime = t
            spectrum = self.capture()
            wl = spectrum[:, 0]
            cts = spectrum[:, 1]
            cps = cts / t  # counts per second
            if i == 0:
                cps_overall = cps
            mask = cts < threshold
            cps_overall[mask] = cps[mask]

        spectrum = np.array([wl, cps_overall]).T
        return spectrum

    def transmission_hdr(self):
        """captures an HDR transmission spectrum
        """
        if self._baseline_light is None:
            raise ValueError(
                "Baselines not taken! .take_light_baseline(), .take_dark_baseline()"
            )
        if self.integrationtime not in self._baseline_light:
            raise ValueError(
                f"Baseline not taken for current integration time ({self.integrationtime}). Taken for {list(self._baseline_light.keys())}"
            )
        for i, t in enumerate(self._hdr_times):
            self.integrationtime = t
            spectrum = self.capture()
            wl = spectrum[:, 0]
            cts = spectrum[:, 1]
            transmission = (cts - self._baseline_dark[t]) / (
                self._baseline_light[t] - self._baseline_dark[t]
            )
            if i == 0:
                transmission_overall = transmission
            mask = cts < t
            transmission_overall[mask] = transmission[mask]

        spectrum = np.array([wl, transmission_overall]).T
        return spectrum

    def estimate_integrationtime(
        self, wlmin: float = -np.inf, wlmax: float = np.inf, target: float = 0.75
    ):
        """finds integration time to hit desired fraction of detector max signal in a given wavelength range


        Args:
            wlmin (float, optional): wavelengths (nm) below this are not considered for exposure time calculation. Defaults to -np.inf.
            wlmax (float, optional): wavelengths (nm) above this are not considered for exposure time calculation. Defaults to np.inf.
            target (float, optional): Fraction of detector saturation (2**16) to target. Defaults to 0.8.

        Raises:
            ValueError: [description]

        Returns:
            [type]: [description]
        """
        if target > 1 or target < 0:
            raise ValueError(
                "Target counts must be between 0-1 (fraction of saturated counts)"
            )
        target *= 2 ** 16  # aim for some fraction of max counts (of 16 bit depth)
        mask = np.logical_and(self.__wl >= wlmin, self.__wl <= wlmax)

        def objective(integrationtime):
            self.integrationtime = integrationtime
            spectrum = self.capture()
            return spectrum[mask, 1].max()

        integrationtime_guesses = np.array([100, 200, 400, 800])
        counts = np.array([objective(it) for it in integrationtime_guesses])
        peakedmask = counts >= (2 ** 16) * 0.95
        p = np.polyfit(integrationtime_guesses[~peakedmask], counts[~peakedmask])

        return np.polyval(p, target).astype(int)

    def take_light_baseline(self):
        """takes an illuminated baseline at each integration time from HDR timings
        """
        self._baseline_light = {}
        for t in self._hdr_times:
            self.integrationtime = t
            spectrum = self.capture()
            self._baseline_light[t] = spectrum[:, 1]

    def take_dark_baseline(self):
        """takes an dark baseline at each integration time from HDR timings
        """
        self._baseline_dark = {}
        for t in self._hdr_times:
            self.integrationtime = t
            spectrum = self.capture()
            self._baseline_dark[t] = spectrum[:, 1]

