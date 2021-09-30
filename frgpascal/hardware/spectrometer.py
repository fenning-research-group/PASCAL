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
        self._hdr_times = [
            50,
            100,
            250,
            500,
            2500,
            15000,
        ]  # duration times (ms) for high dynamic range measurements
        self.HDR_THRESHOLD = (
            2 ** 16 * 0.95
        )  # counts above this are considered saturated
        self.SETTING_DELAY = (
            0.2  # seconds between changing a setting and having it take effect
        )

        print("Connected to spectrometer")
        self.dwelltime = self._hdr_times[0]  # ms
        self.numscans = 1  # one scan per spectrum
        self.smooth = 0  # smoothing factor, units unclear

        self.__baseline_dark = {}
        self.__baseline_light = {}

    @property
    def dwelltime(self):
        return self.__integrationtime

    @dwelltime.setter
    def dwelltime(self, t):
        self.id["device"].set_config(int_time=t)
        time.sleep(self.SETTING_DELAY)
        self.__integrationtime = t

    @property
    def numscans(self):
        return self.__numscans

    @numscans.setter
    def numscans(self, n):
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
        for t in self._hdr_times:
            if skip_repeats and t in self.__baseline_light:
                continue  # already taken
            self.dwelltime = t
            wl, cts = self._capture_raw()
            self.__baseline_light[t] = cts

    def take_dark_baseline(self, skip_repeats=False):
        """takes an dark baseline at each integration time from HDR timings"""
        for t in self._hdr_times:
            if skip_repeats and t in self.__baseline_dark:
                continue  # already taken
            self.dwelltime = t
            wl, cts = self._capture_raw()
            self.__baseline_dark[t] = cts

    def __is_dark_baseline_taken(self, dwelltime=None):
        """Check whether a baseline has been taken at the current integration time

        Raises:
            ValueError: Dark baseline has not been taken at the current integration time

        Returns True if dark baseline has been taken at the current integration time
        """
        if dwelltime is None:
            dwelltime = self.dwelltime
        if dwelltime not in self.__baseline_dark:
            raise ValueError(
                f"Dark baseline not taken for current integration time ({self.dwelltime} ms). Taken for {list(self.__baseline_dark.keys())}"
            )

        return True

    def __is_light_baseline_taken(self, dwelltime=None):
        """Check whether a baseline has been taken at the current integration time

        Raises:
            ValueError: Light baseline has not been taken at the current integration time

        Returns True if light baseline has been taken at the current integration time
        """
        if dwelltime is None:
            dwelltime = self.dwelltime
        if dwelltime not in self.__baseline_light:
            raise ValueError(
                f"Illuminated baseline not taken for current integration time ({self.dwelltime}). Taken for {list(self.__baseline_light.keys())}"
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

        returns counts/second with dark baseline subtracted.
        saturated counts are set to np.nan
        """
        if self.__is_dark_baseline_taken():
            wl, cts = self._capture_raw()
            cts[cts >= (2 ** 16 - 1)] = np.nan  # detector saturated here
            cts -= self.__baseline_dark[self.dwelltime]
            return wl, cts

    def capture_hdr(self):
        """captures an HDR spectrum by combining acquisitions at multiple integration times

        returns spectrum in *counts per second*
        """
        if not all([self.__is_dark_baseline_taken(t) for t in self._hdr_times]):
            return  # error will be thrown by __is_dark_baseline_taken()

        for i, t in enumerate(self._hdr_times):
            self.dwelltime = t  # milliseconds
            wl, cts_raw = self._capture_raw()
            cts = cts_raw - self.__baseline_dark[t]
            cps = cts / (t / 1000)  # counts per second
            if i == 0:
                cps_overall = cps
            else:
                mask = cts_raw < self.HDR_THRESHOLD
                cps_overall[mask] = cps[mask]

        return wl, cps_overall

    def transmission(self):
        """
        captures a transmission spectrum
        """
        t = self.dwelltime
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
                for t in self._hdr_times
            ]
        ):
            return  # error will be thrown by __is_light_baseline_taken() or __is_dark_baseline_taken()

        for i, t in enumerate(self._hdr_times):
            self.dwelltime = t  # milliseconds
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
                mask = self.__baseline_light[t] < self.HDR_THRESHOLD
                transmission_overall[mask] = transmission[mask]

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


class DummySpectrometer:
    """Empty object to pantomime a Stellarnet spectrometer.
    Used for testing while spectrometer was in use for other experiments.
    """

    def __init__(self, address=0):
        # self.id, self.__wl = sn.array_get_spec(address)
        self.id = None
        self.__wl = np.linspace(200, 1200, 400)  # random wavelength range
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
        # self.id["device"].set_config(int_time=t)
        self.__integrationtime = t

    @property
    def numscans(self):
        return self.__numscans

    @numscans.setter
    def numscans(self, n):
        # self.id["device"].set_config(scans_to_avg=n)
        self.__numscans = n

    @property
    def smooth(self):
        return self.__smooth

    @smooth.setter
    def smooth(self, n):
        # self.id["device"].set_config(x_smooth=n)
        self.__smooth = n

    def capture(self):
        """
        captures a spectrum from the usb spectrometer
        """
        # spectrum = sn.array_spectrum(self.id, self.__wl)
        spectrum = np.vstack((self.__wl, np.random.rand(len(self.__wl))))
        spectrum[:, 1] /= self.integrationtime  # convert to counts per second
        return spectrum

    def capture_hdr(self):
        """captures an HDR spectrum"""
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

    def transmission(self):
        if (self._baseline_light is None) or (self._baseline_dark is None):
            raise ValueError(
                "Baselines not taken! .take_light_baseline(), .take_dark_baseline()"
            )
        if self.integrationtime not in self._baseline_light:
            raise ValueError(
                f"Baseline not taken for current integration time ({self.integrationtime}). Taken for {list(self._baseline_light.keys())}"
            )

        spectrum = self.capture()
        wl = spectrum[:, 0]
        cts = spectrum[:, 1]

        t = self.integrationtime
        transmission = (cts - self._baseline_dark[t]) / (
            self._baseline_light[t] - self._baseline_dark[t]
        )

        spectrum = np.array([wl, transmission]).T
        return spectrum

    def transmission_hdr(self):
        """captures an HDR transmission spectrum"""
        if (self._baseline_light is None) or (self._baseline_dark is None):
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
        """takes an illuminated baseline at each integration time from HDR timings"""
        self._baseline_light = {}
        for t in self._hdr_times:
            self.integrationtime = t
            spectrum = self.capture()
            self._baseline_light[t] = spectrum[:, 1]

    def take_dark_baseline(self):
        """takes an dark baseline at each integration time from HDR timings"""
        self._baseline_dark = {}
        for t in self._hdr_times:
            self.integrationtime = t
            spectrum = self.capture()
            self._baseline_dark[t] = spectrum[:, 1]
