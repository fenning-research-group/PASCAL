import os
import numpy as np
import json

from frgpascal.analysis import darkfield, brightfield, photoluminescence, transmittance


def process_sample(sample: str, datadir: str):
    sampledir = os.path.join(datadir, sample)
    if not os.path.exists(sampledir):
        raise Exception(f"Characterization data not found for {sample} in {datadir}")

    cidx = -1

    metrics = {}
    while True:
        cidx += 1
        chardir = os.path.exists(
            os.path.join(sampledir, f"characterization{cidx}.json")
        )
        if not os.path.exists(chardir):
            break

        charfids = os.listdir(chardir)

        plfid = os.path.join(chardir, f"{sample}_pl.csv")
        if plfid in charfids:
            wl, cps = photoluminescence.load_spectrum(plfid)
            plfit = photoluminescence.fit_spectrum(
                wl=wl, cts=cps, wlmin=640, wlmax=1100, plot=False
            )
            metrics[f"pl_intensity_{cidx}"] = plfit["intensity"]
            metrics[f"pl_peakev_{cidx}"] = plfit["peakev"]
            metrics[f"pl_fwhm_{cidx}"] = plfit["fwhm"]

        psfid = os.path.join(chardir, f"{sample}_photostability.csv")
        if psfid in charfids:
            time, wl, cps = photoluminescence.load_spectrum(plfid)
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
        if tfid in charfids:
            wl, t = transmittance.load_spectrum(tfid)
            a = -np.log10(t)
            metrics["t_bandgap_{cidx}"] = transmittance.tauc(
                wl=wl, a=a, bandgap_type="direct", wlmin=400, wlmax=1050, plot=False
            )

        dffid = os.path.join(chardir, f"{sample}_darkfield.csv")
        if dffid in charfids:
            img = darkfield.load_image(dffid, red_only=True)
            metrics["df_median_{cidx}"] = darkfield.get_median(im=img)

    return metrics
