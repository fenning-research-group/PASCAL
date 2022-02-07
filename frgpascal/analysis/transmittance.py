import numpy as np


def load_spectrum(fid):
    d = np.loadtxt(fid, delimiter=",", skiprows=2)
    wl = d[:, 0]
    t = d[:, 1]
    return wl, t


def tauc(
    wl,
    a,
    bandgap_type,
    wlmin=None,
    wlmax=None,
    fit_width=None,
    fit_threshold=0.1,
    plot=False,
    verbose=False,
):
    """
    Performs Tauc plotting analysis to determine optical bandgap from absorbance data
    Plots data in tauc units, then performs linear fits in a moving window to find the
    best linear region. this best fit line is extrapolated to the x-axis, which corresponds
    to the bandgap.

    inputs

            wl: array of wavelengths (nm)
            a: absorption coefficient. Absorbance can also be used - while the plot will be stretched in y, a scalar factor here doesnt affect the bandgap approximation
            thickness: sample thickness (cm)
            bandgap_type: ['direct', 'indirect']. determines coefficient on tauc value

            wlmin: minimum wavelength (nm) to include in plot
            wlmax: maximum wavelenght (nm) to include in plot
            fit_width: width of linear fit window, in units of wl, a vector indices
            fit_threshold: window values must be above this fraction of maximum tauc value.
                                            prevents fitting region before the absorption onset
            plot: boolean flag to generate plot of fit
            verbose: boolean flag to (True) generate detailed output or (False) just output Eg

    output (verbose = False)
            bandgap: optical band gap (eV)

    output (verbose = True)
            dictionary with values:
                    bandgap: optical band gap (eV)
                    r2: r-squared value of linear fit
                    bandgap_min: minimum bandgap within 95% confidence interval
                    bandgap_max: maximum bandgap within 95% confidence interval
    """
    wl = np.array(wl)
    if wlmin is None:
        wlmin = wl.min()
    if wlmax is None:
        wlmax = wl.max()
    wlmask = np.where((wl >= wlmin) & (wl <= wlmax))

    wl = wl[wlmask]
    a = np.array(a)[wlmask]

    if fit_width is None:
        fit_width = len(wl) // 20  # default to 5% of data width

    fit_pad = fit_width // 2

    if str.lower(bandgap_type) == "direct":
        n = 0.5
    elif str.lower(bandgap_type) == "indirect":
        n = 2
    else:
        raise ValueError(
            'argument "bandgap_type" must be provided as either "direct" or "indirect"'
        )

    c = 3e8  # speed of light, m/s
    h = 4.13567e-15  # planck's constant, eV
    nu = c / (wl * 1e-9)  # convert nm to hz
    ev = 1240 / wl  # convert nm to ev

    taucvalue = (a * h * nu) ** (1 / n)
    taucvalue_threshold = taucvalue.max() * fit_threshold
    best_slope = None
    best_intercept = None
    best_r2 = 0

    for idx in range(fit_pad, len(wl) - fit_pad):
        if taucvalue[idx] >= taucvalue_threshold:
            fit_window = slice(idx - fit_pad, idx + fit_pad)
            slope, intercept, rval, _, stderr = linregress(
                ev[fit_window], taucvalue[fit_window]
            )
            r2 = rval ** 2
            if r2 > best_r2 and slope > 0:
                best_r2 = r2
                best_slope = slope
                best_intercept = intercept

    Eg = -best_intercept / best_slope  # x intercept

    if plot:
        fig, ax = plt.subplots()
        ax.plot(ev, taucvalue, "k")
        ylim0 = ax.get_ylim()
        ax.plot(
            ev, ev * best_slope + best_intercept, color=plt.cm.tab10(3), linestyle=":"
        )
        ax.set_ylim(*ylim0)
        ax.set_xlabel("Photon Energy (eV)")
        if n == 0.5:
            ax.set_ylabel(r"$({\alpha}h{\nu})^2$")
        else:
            ax.set_ylabel(r"$({\alpha}h{\nu})^{1/2}$")
        plt.show()

    if not verbose:
        return Eg
    else:
        ### calculate 95% CI of Eg
        mx = ev.mean()
        sx2 = ((ev - mx) ** 2).sum()
        sd_intercept = stderr * np.sqrt(1.0 / len(ev) + mx * mx / sx2)
        sd_slope = stderr * np.sqrt(1.0 / sx2)

        Eg_min = -(best_intercept - 1.96 * sd_intercept) / (
            best_slope + 1.96 * sd_slope
        )
        Eg_max = -(best_intercept + 1.96 * sd_intercept) / (
            best_slope - 1.96 * sd_slope
        )

        output = {
            "bandgap": Eg,
            "r2": best_r2,
            "bandgap_min": Eg_min,
            "bandgap_max": Eg_max,
        }
        return output
