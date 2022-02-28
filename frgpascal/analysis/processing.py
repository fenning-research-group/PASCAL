import os
import numpy as np
import pandas as pd
from typing import Tuple

from frgpascal.analysis import darkfield, brightfield, photoluminescence, transmittance


def load_sample(sample: str, datadir: str) -> Tuple[dict, dict]:
    """Loads all available characterization data + extracts standard metrics for a given sample

    Args:
        sample (str): name of sample
        datadir (str): directory in which characterization data is stored

    Raises:
        Exception: Folder for sample name not found in characterization data directory

    Returns:
        Tuple[dict, dict]: dictionary of extracted metrics, dictionary of raw data
    """
    sampledir = os.path.join(datadir, sample)
    if not os.path.exists(sampledir):
        raise Exception(f"Characterization data not found for {sample} in {datadir}")

    cidx = -1

    metrics = {}
    raw = {}

    while True:
        cidx += 1
        chardir = os.path.join(sampledir, f"characterization{cidx}")
        if not os.path.exists(chardir):
            break

        plfid = os.path.join(chardir, f"{sample}_pl.csv")
        if os.path.exists(plfid):
            wl, cps = photoluminescence.load_spectrum(plfid)
            raw[f"pl_{cidx}"] = {
                "wl": wl,
                "cps": cps,
            }
            plfit = photoluminescence.fit_spectrum(
                wl=wl, cts=cps, wlmin=640, wlmax=1100, plot=False
            )
            metrics[f"pl_intensity_{cidx}"] = plfit["intensity"]
            metrics[f"pl_peakev_{cidx}"] = plfit["peakev"]
            metrics[f"pl_fwhm_{cidx}"] = plfit["fwhm"]

        psfid = os.path.join(chardir, f"{sample}_photostability.csv")
        if os.path.exists(psfid):
            time, wl, cps = photoluminescence.load_photostability(psfid)
            raw[f"ps_{cidx}"] = {
                "time": time,
                "wl": wl,
                "cps": cps,
            }
            psfit = photoluminescence.fit_photostability(
                times=time, wl=wl, cts=cps, wlmin=640, wlmax=1100, plot=False
            )
            metrics[f"ps_intensity_scale_{cidx}"] = psfit["intensity"][
                "scale_norm"
            ]  # final intensity / initial intensity
            metrics[f"ps_intensity_rate_{cidx}"] = psfit["intensity"][
                "rate"
            ]  # time constant for exponential decay/rise
            metrics[f"ps_peakev_delta_{cidx}"] = psfit["peakev"][
                "delta"
            ]  # final peakev / initial peakev
            metrics[f"ps_peakev_rate_{cidx}"] = psfit["peakev"][
                "rate"
            ]  # final peakev / initial peakev

        tfid = os.path.join(chardir, f"{sample}_transmission.csv")
        if os.path.exists(tfid):
            wl, t = transmittance.load_spectrum(tfid)
            a = -np.log10(t)

            raw[f"t_{cidx}"] = {
                "wl": wl,
                "t": t,
                "a": a,
            }
            try:
                metrics[f"t_bandgap_{cidx}"] = transmittance.tauc(
                    wl=wl, a=a, bandgap_type="direct", wlmin=400, wlmax=1050, plot=False
                )
            except:
                metrics[f"t_bandgap_{cidx}"] = np.nan

        dffid = os.path.join(chardir, f"{sample}_darkfield.tif")
        if os.path.exists(dffid):
            img = darkfield.load_image(dffid, red_only=False)
            raw[f"df_{cidx}"] = img
            metrics[f"df_median_{cidx}"] = darkfield.get_median(
                im=img[:, :, 0]
            )  # median counts on red channel

        bffid = os.path.join(chardir, f"{sample}_brightfield.tif")
        if os.path.exists(bffid):
            img = brightfield.load(bffid)
            raw[f"bf_{cidx}"] = img
            # metrics[f"bf_homogeneity_{cidx}"] = brightfield.(
            #     im=img
            # )

    return metrics, raw


def load_all(datadir: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads + processes all characterization data, returns as DataFrame's

    Args:
        datadir (str): directory in which characterization data is stored

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: dataframe with all fitted metrics from acquired data, dataframe with all raw data
    """

    all_samples = [
        s for s in os.listdir(datadir) if os.path.isdir(os.path.join(datadir, s))
    ]
    all_metrics = {}
    all_raw = {}
    for s in all_samples:
        try:
            all_metrics[s], all_raw[s] = load_sample(sample=s, datadir=datadir)
        except:
            print(f"Could not load data for sample {s}")
    metric_df = pd.DataFrame(all_metrics).T
    raw_df = pd.DataFrame(all_raw).T
    return metric_df, raw_df
