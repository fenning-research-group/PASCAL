import os
import numpy as np
import json

from frgpascal.analysis import darkfield, brightfield, photoluminescence, transmittance
from frgpascal.experimentaldesign.characterizationtasks import PLPhotostability


def process_sample(sample: str, datadir: str):
    sampledir = os.path.join(datadir, sample)
    if not os.path.exists(sampledir):
        raise Exception(f"Characterization data not found for {sample} in {datadir}")

    cidx = -1

    metrics = {}
    while True:
        cidx += 1
        chardir = os.path.join(sampledir, f"characterization{cidx}")
        if not os.path.exists(chardir):
            break

        plfid = os.path.join(chardir, f"{sample}_pl.csv")
        if os.path.exists(plfid):
            wl, cps = photoluminescence.load_spectrum(plfid)
            plfit = photoluminescence.fit_spectrum(
                wl=wl, cts=cps, wlmin=640, wlmax=1100, plot=False
            )
            metrics[f"pl_intensity_{cidx}"] = plfit["intensity"]
            metrics[f"pl_peakev_{cidx}"] = plfit["peakev"]
            metrics[f"pl_fwhm_{cidx}"] = plfit["fwhm"]

        psfid = os.path.join(chardir, f"{sample}_photostability.csv")
        if os.path.exists(psfid):
            time, wl, cps = photoluminescence.load_photostability(psfid)
            psfit = photoluminescence.fit_photostability(
                times=time, wl=wl, cts=cps, wlmin=640, wlmax=1100, plot=False
            )
            metrics[f"ps_intensity_scale_{cidx}"] = psfit["intensity"][
                "scale_norm"
            ]  # final intensity / initial intensity
            metrics[f"ps_intensity_rate_{cidx}"] = psfit["intensity"][
                "rate"
            ]  # time constant for exponential decay/rise
            metrics[f"ps_peakev_delta_{cidx}"] = plfit["peakev"][
                "delta"
            ]  # final peakev / initial peakev
            metrics[f"ps_peakev_rate_{cidx}"] = plfit["peakev"][
                "rate"
            ]  # final peakev / initial peakev

        tfid = os.path.join(chardir, f"{sample}_transmission.csv")
        if os.path.exists(tfid):
            wl, t = transmittance.load_spectrum(tfid)
            a = -np.log10(t)
            metrics[f"t_bandgap_{cidx}"] = transmittance.tauc(
                wl=wl, a=a, bandgap_type="direct", wlmin=400, wlmax=1050, plot=False
            )

        dffid = os.path.join(chardir, f"{sample}_darkfield.tif")
        if os.path.exists(dffid):
            img = darkfield.load_image(dffid, red_only=True)
            metrics[f"df_median_{cidx}"] = darkfield.get_median(im=img)

    return metrics
