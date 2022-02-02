from multiprocessing.sharedctypes import Value
import sys
import os
import time

sys.path.append(os.path.dirname(__file__))

import numpy as np
import stellarnet_driver3 as sn  # usb driver

### https://stackoverflow.com/questions/15457786/ctrl-c-crashes-python-after-importing-scipy-stats
# os.environ[
#     "FOR_DISABLE_CONSOLE_CTRL_HANDLER"
# ] = "1"  # to preserve ctrl-c with scipy loaded
# from scipy.optimize import minimize


class Spectrometer:
    """Object to interface with Stellarnet spectrometer"""

    def __init__(self, address=0):
        self.id, self.__wl = sn.array_get_spec(address)
        self._exposure_times = [
            0.05,
            0.1,
            0.25,
            0.5,
            2.5,
            15.0,
        ]  # duration times (ms) for high dynamic range measurements
        self.CTS_THRESHOLD = (
            2 ** 16 * 0.98
        )  # counts above this are considered saturated
        self.SETTING_DELAY = (
            0.2  # seconds between changing a setting and having it take effect
        )

        print("Connected to spectrometer")
        self.exposure_time = self._exposure_times[0]  # ms
        self.num_scans = 1  # one scan per spectrum
        self.smooth = 0  # smoothing factor, units unclear.

        self.__baseline_dark = {}
        self.__baseline_light = {}

    @property
    def exposure_time(self):
        return self.__integrationtime

    @exposure_time.setter
    def exposure_time(self, t):
        if t < 0.02 or t > 60:
            raise ValueError(
                "Spectrometer dwelltime must be between .02 and 60 seconds!"
            )
        newtime = int(
            t * 1e3
        )  # convert seconds to milliseconds - spectrometer expects ms
        self.id["device"].set_config(int_time=newtime)
        time.sleep(self.SETTING_DELAY)
        self.__integrationtime = t

    @property
    def num_scans(self):
        return self.__numscans

    @num_scans.setter
    def num_scans(self, n):
        self.id["device"].set_config(scans_to_avg=n)
        time.sleep(self.SETTING_DELAY)
        self.__numscans = n

    @property
    def smooth(self):
        return self.__smooth

    @smooth.setter
    def smooth(self, n):
        if n not in [0, 1, 2, 3, 4]:
            raise ValueError("Smoothing factor must be 0, 1, 2, 3, or 4")
        self.id["device"].set_config(x_smooth=n)
        time.sleep(self.SETTING_DELAY)
        self.__smooth = n

    def take_light_baseline(self, skip_repeats=False):
        """takes an illuminated baseline at each integration time from HDR timings"""
        numscans0 = self.num_scans
        self.num_scans = 3
        for t in self._exposure_times:
            if skip_repeats and t in self.__baseline_light:
                continue  # already taken
            self.exposure_time = t
            wl, cts = self._capture_raw()
            self.__baseline_light[t] = cts
        self.num_scans = numscans0

    def take_dark_baseline(self, skip_repeats=False):
        """takes an dark baseline at each integration time from HDR timings"""
        numscans0 = self.num_scans
        self.num_scans = 3
        for t in self._exposure_times:
            if skip_repeats and t in self.__baseline_dark:
                continue  # already taken
            self.exposure_time = t
            wl, cts = self._capture_raw()
            self.__baseline_dark[t] = cts
        self.num_scans = numscans0

    def __is_dark_baseline_taken(self, dwelltime=None):
        """Check whether a baseline has been taken at the current integration time

        Raises:
            ValueError: Dark baseline has not been taken at the current integration time

        Returns True if dark baseline has been taken at the current integration time
        """
        if dwelltime is None:
            dwelltime = self.exposure_time
        if dwelltime not in self.__baseline_dark:
            raise ValueError(
                f"Dark baseline not taken for current integration time ({self.exposure_time} ms). Taken for {list(self.__baseline_dark.keys())}"
            )

        return True

    def __is_light_baseline_taken(self, dwelltime=None):
        """Check whether a baseline has been taken at the current integration time

        Raises:
            ValueError: Light baseline has not been taken at the current integration time

        Returns True if light baseline has been taken at the current integration time
        """
        if dwelltime is None:
            dwelltime = self.exposure_time
        if dwelltime not in self.__baseline_light:
            raise ValueError(
                f"Illuminated baseline not taken for current integration time ({self.exposure_time}). Taken for {list(self.__baseline_light.keys())}"
            )

        return True

    def _capture_raw(self):
        """
        captures a spectrum from the usb spectrometer

        returns raw wavelength + counts read from spectrometer
        """
        spectrum = sn.array_spectrum(self.id, self.__wl)
        # spectrum[:, 1] /= self.integrationtime / 1000  # convert to counts per second
        wl, cts = (
            spectrum[:, 0].round(2),
            spectrum[:, 1],
        )  # wavelength bins are reported as way more precise than they actually are for our slit width
        return wl, cts

    def capture(self):
        """
        captures a spectrum from the usb spectrometer

        returns counts with dark baseline subtracted.
        saturated counts are set to np.nan
        """
        if self.__is_dark_baseline_taken():
            wl, cts = self._capture_raw()
            cts[cts >= (2 ** 16 - 1)] = np.nan  # detector saturated here
            cts -= self.__baseline_dark[self.exposure_time]
            return wl, cts

    def capture_hdr(self):
        """captures an HDR spectrum by combining acquisitions at multiple integration times

        returns spectrum in *counts per second*
        """
        if not all([self.__is_dark_baseline_taken(t) for t in self._exposure_times]):
            return  # error will be thrown by __is_dark_baseline_taken()

        for i, t in enumerate(self._exposure_times):
            self.exposure_time = t  # milliseconds
            wl, cts_raw = self._capture_raw()
            cts = cts_raw - self.__baseline_dark[t]
            cps = cts / (t / 1000)  # counts per second
            if i == 0:
                cps_overall = cps
            else:
                mask = cts_raw < self.CTS_THRESHOLD
                cps_overall[mask] = cps[mask]

        return wl, cps_overall

    def transmission(self):
        """
        captures a transmission spectrum
        """
        t = self.exposure_time
        if not self.__is_light_baseline_taken(t) and self.__is_dark_baseline_taken(t):
            return  # error will be thrown by __is_light_baseline_taken() or __is_dark_baseline_taken()

        wl, cts = self.capture()  # removes dark baseline from captured spectrum
        transmission = cts / (self.__baseline_light[t] - self.__baseline_dark[t])
        return wl, transmission

    def transmission_hdr(self):
        """captures an HDR transmission spectrum"""
        if not all(
            [
                self.__is_light_baseline_taken(t) and self.__is_dark_baseline_taken(t)
                for t in self._exposure_times
            ]
        ):
            return  # error will be thrown by __is_light_baseline_taken() or __is_dark_baseline_taken()

        for i, t in enumerate(self._exposure_times):
            self.exposure_time = t  # milliseconds
            (
                wl,
                cts,
            ) = self._capture_raw()  # removes dark baseline from captured spectrum
            transmission = (cts - self.__baseline_dark[t]) / (
                self.__baseline_light[t] - self.__baseline_dark[t]
            )
            if i == 0:
                transmission_overall = transmission
            else:
                mask = self.__baseline_light[t] < self.CTS_THRESHOLD
                transmission_overall[mask] = transmission[mask]

        self.exposure_time = self._exposure_times[0]
        return wl, transmission_overall

    # def estimate_integrationtime(
    #     self, wlmin: float = -np.inf, wlmax: float = np.inf, target: float = 0.75
    # ):
    #     """finds integration time to hit desired fraction of detector max signal in a given wavelength range

    #     Args:
    #         wlmin (float, optional): wavelengths (nm) below this are not considered for exposure time calculation. Defaults to -np.inf.
    #         wlmax (float, optional): wavelengths (nm) above this are not considered for exposure time calculation. Defaults to np.inf.
    #         target (float, optional): Fraction of detector saturation (2**16) to target. Defaults to 0.8.

    #     Raises:
    #         ValueError: [description]

    #     Returns:
    #         [type]: [description]
    #     """
    #     if target > 1 or target < 0:
    #         raise ValueError(
    #             "Target counts must be between 0-1 (fraction of saturated counts)"
    #         )
    #     target *= 2 ** 16  # aim for some fraction of max counts (of 16 bit depth)
    #     mask = np.logical_and(self.__wl >= wlmin, self.__wl <= wlmax)

    #     def objective(integrationtime):
    #         self.dwelltime = integrationtime
    #         spectrum = self.capture()
    #         return spectrum[mask, 1].max()

    #     integrationtime_guesses = np.array([100, 200, 400, 800])
    #     counts = np.array([objective(it) for it in integrationtime_guesses])
    #     peakedmask = counts >= (2 ** 16) * 0.95
    #     p = np.polyfit(integrationtime_guesses[~peakedmask], counts[~peakedmask])

    #     return np.polyval(p, target).astype(int)
