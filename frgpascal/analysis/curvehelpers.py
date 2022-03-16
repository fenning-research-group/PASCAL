import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

### Gaussian curves


def gaussian(x, amplitude, center, sigma):
    return amplitude * np.exp(-((x - center) ** 2) / (2 * sigma**2))


def fit_gaussian(
    x_nm, y, fit_range=(650, 1100), ev_guess=None, plot=False, adjust_baseline=False
):
    x_ev = 1240 / x_nm
    if adjust_baseline:
        bl = np.mean(y[x_ev < 500])
        y = y - bl

    fit_mask = (x_nm > fit_range[0]) & (x_nm < fit_range[1])
    x_fit = x_ev[fit_mask]
    y_fit = y[fit_mask]
    if ev_guess is None:
        ev_guess = x_fit[np.argmax(y_fit)]

    ev_guess_min = max(ev_guess - 0.2, x_ev.min())
    ev_guess_max = min(ev_guess + 0.2, x_ev.max())
    bounds = [[0, ev_guess_min, 0.02], [y_fit.max() * 1.2, ev_guess_max, 0.05]]

    p0 = [y_fit.max(), ev_guess, 0.025]

    #     y0 = np.mean(y[y-y.min() < y.std()])
    try:
        popt, _ = curve_fit(gaussian, x_fit, y_fit, p0=p0, bounds=bounds)
        out = {
            "intensity": popt[0],
            "peakev": popt[1],
            "fwhm": 2.355 * popt[2],  # sigma -> fwhm
            "wl": x_nm,
            "cps": gaussian(x_ev, *popt),
        }
        if plot:
            plt.figure()
            plt.scatter(x_ev, y, color="k", s=2)
            plt.plot(x_ev, gaussian(x_ev, *popt), color="r")
    except:
        out = {
            "intensity": np.nan,
            "peakev": np.nan,
            "fwhm": np.nan,
            "wl": x_nm,
            "cps": y,
        }
        print("error fitting PL")
    return out


def fit_gaussian_series(
    wl, cts, fit_range=(650, 1100), wlguess=None, plot=False, adjust_baseline=False
):
    out = []
    if wlguess is None:
        ev_guess = None
    else:
        ev_guess = 1240 / wlguess
    for i, cts_ in enumerate(cts):
        out.append(
            fit_gaussian(
                wl,
                cts_,
                fit_range=fit_range,
                ev_guess=ev_guess,
                plot=plot,
                adjust_baseline=adjust_baseline,
            )
        )
        ev_guess = out[-1]["peakev"]
    outseries = {k: [] for k in out[0].keys()}
    for o in out:
        for k in o.keys():
            outseries[k].append(o[k])
    return outseries


### Exponential curves


def exponential(x, scale, rate, offset):
    """
    fits an exponential decay curve
    """
    return offset - scale * np.exp(-rate * x)


def fit_exponential(x, y):
    bounds = [[-np.inf, 0, 0], [np.inf, 1, np.inf]]
    p0 = [y[0] - y[-1], 0.02, y[-1]]
    try:
        popt, _ = curve_fit(exponential, x, y, p0=p0, bounds=bounds)
    except:
        popt = [np.nan, np.nan, np.nan]
    return {"scale": popt[0], "rate": popt[1], "offset": popt[2]}


### Planes
def plane(x: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    """computes z values for a 2-D plane

    Args:
        x (np.ndarray): 2-D array of [n x 2], where x,y are columns
        a (float): slope with respect to x
        b (float): slope with respect to y
        c (float): intercept

    Returns:
        np.ndarray: values of z for each x,y pair
    """
    return a * x[:, 0] + b * x[:, 1] + c


def fit_plane_to_image(img: np.ndarray) -> dict:
    """given a 2d array, finds a best-fit plane through the surface

    Args:
        img (np.ndarray): 2d array of z values per x,y coordinate (note that x,y coordinates here are array indices)


    Returns:
        dict: parameters describing plane of form z = ax + by + c
    """
    xc, yc = np.meshgrid(np.arange(img.shape[0]), np.arange(img.shape[1]))
    x = np.hstack([xc.reshape(-1, 1), yc.reshape(-1, 1)])

    popt, pcov = curve_fit(
        f=plane,
        xdata=x,
        ydata=img.ravel(),
        p0=[0, 0, img.mean()],
    )
    return {
        "a": popt[0],
        "b": popt[1],
        "c": popt[2],
        "plane": plane(x, *popt).reshape(img.shape),
    }
