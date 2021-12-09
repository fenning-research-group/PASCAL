import numpy as np
import matplotlib.pyplot as plt
from curvehelpers import (
    gaussian,
    fit_gaussian,
    fit_gaussian_series,
    exponential,
    fit_exponential,
)
from scipy.optimize import curve_fit


def load_spectrum(fid):
    """
    loads a photoluminescence spectrum from the PASCAL csv file format for
    a single shot PL spectrum.

    The longest dwell time spectrum without any saturated pixels will be
    normalized by the dwell time to return counts per second
    """
    with open(fid, "r") as f:
        dwelltimes = [float(dwell) for dwell in f.readline().split(",")[1:]]

    d = np.loadtxt(fid, delimiter=",", skiprows=2)

    wl = d[:, 0]
    for i in range(d.shape[1] - 1, 0, -1):
        if not any(np.isnan(d[:, i])):
            break
    cps = (
        1000 * d[:, i] / dwelltimes[i - 1]
    )  # normalize by dwelltime (milliseconds), convert counts/ms to counts/s
    return wl, cps


def load_photostability(fid):
    """
    loads a series of photoluminescence spectra from the PASCAL csv file format
    for a timeseries of PL spectra.

    The spectra are each normalized to the dwell time to return counts per second
    """
    with open(fid, "r") as f:
        dwelltime = float(f.readline().split(",")[1])  # dwelltime, in milliseconds
        for i in range(2):
            f.readline()  # skip rest of header
        times = [float(t) for t in f.readline().split(",")[1:]]

    d = np.loadtxt(fid, delimiter=",", skiprows=4)
    wl = d[:, 0]
    cps = 1000 * d[:, 1:].T / dwelltime  # dwelltime in ms, convert to cts/second
    blcts = np.mean(cps[:, wl < 500], axis=1)
    cps -= blcts[:, np.newaxis]

    return times, wl, cps


def fit_spectrum(wl, cts, wlmin, wlmax, wlguess=None, plot=False):
    ev = 1240 / wl
    evmin = 1240 / wlmax
    evmax = 1240 / wlmin

    fit_mask = (ev >= evmin) & (ev <= evmax)
    ev_fit = ev[fit_mask]
    y_fit = cts[fit_mask]
    if wlguess is None:
        ev_guess = ev_fit[np.argmax(y_fit)]
    else:
        ev_guess = 1240 / wlguess

    ev_guess_min = max(ev_guess - 0.2, ev.min())
    ev_guess_max = min(ev_guess + 0.2, ev.max())
    bounds = [[0, ev_guess_min, 0.02], [y_fit.max() * 1.2, ev_guess_max, 0.05]]

    p0 = [y_fit.max(), ev_guess, 0.025]

    popt, _ = curve_fit(gaussian, ev_fit, y_fit, p0=p0, bounds=bounds)
    out = {
        "intensity": popt[0],
        "peakev": popt[1],
        "fwhm": 2.355 * popt[2],  # sigma -> fwhm
        "wl": wl,
        "ev": ev,
        "cps": gaussian(ev, *popt),
    }
    if plot:
        plt.figure()
        plt.scatter(ev, y, color="k", s=2)
        plt.plot(ev, gaussian(ev, *popt), color="r")


def fit_photostability(times, wl, cts, wlmin, wlmax, wlguess=None, plot=False):
    series = fit_gaussian_series(
        wl, cts, fit_range=(wlmin, wlmax), wlguess=wlguess, adjust_baseline=False
    )

    if np.nanmax(series["intensity"]) < 0.15:
        raise Exception("No visible pl data")
    x = fit_exponential(times, series["intensity"])
    scale = x["scale"]
    rate = x["rate"]
    saturation = x["offset"]
    x = fit_exponential(times, series["peakev"])
    evscale = x["scale"]
    evrate = x["rate"]
    evsaturation = x["offset"]

    if plot:
        fig, ax = plt.subplots(1, 3, figsize=(12, 4))
        for i, (c, cfit) in enumerate(zip(cts, series["cps"])):
            ax[0].scatter(wl, c, color=plt.cm.viridis(i / len(cts)), s=2)
            ax[0].plot(wl, cfit, color=plt.cm.viridis(i / len(series["cps"])))
            ax[0].set_xlim(650, 900)
        ax[1].scatter(times, series["intensity"])
        ax[1].plot(times, exponential(np.asarray(times), scale, rate, saturation))
        ax[2].scatter(times, series["peakev"])
        ax[2].plot(times, exponential(np.asarray(times), evscale, evrate, evsaturation))

        ax[0].set_xlabel("Wavelength (nm)")
        for ax_ in ax[:2]:
            ax_.set_ylabel("Counts/second")
        for ax_ in ax[1:]:
            ax_.set_xlabel("Time (s)")
        ax[2].set_ylabel("Emission Center (eV)")

        plt.tight_layout()
        plt.show()

    return dict(
        intensity=dict(
            scale=scale,
            scale_norm=scale / series["intensity"][0],
            rate=rate,
            saturation=saturation,
        ),
        peakev=dict(
            scale=evscale, scale_norm=evscale / series["ev"][0], saturation=evsaturation
        ),
    )
