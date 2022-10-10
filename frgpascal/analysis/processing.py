import os
import numpy as np
import pandas as pd
from typing import Tuple

from frgpascal import analysis
from tqdm import tqdm
from natsort import natsorted
import json


def load_sample(
    sample: str,
    datadir: str,
    photoluminescence=True,
    photostability=True,
    transmission=True,
    brightfield=True,
    darkfield=True,
    plimg=True,
    pl_kwargs={},
    ps_kwargs={},
    t_kwargs={},
    bf_kwargs={},
    df_kwargs={},
    plimg_kwargs={},
) -> Tuple[dict, dict]:
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

        if photoluminescence:
            plfid = os.path.join(chardir, f"{sample}_pl.csv")
            if os.path.exists(plfid):
                wl, cps = analysis.photoluminescence.load_spectrum(plfid)
                raw[f"pl_{cidx}"] = {
                    "wl": wl,
                    "cps": cps,
                }
                pl_kws = dict(wlmin=675, wlmax=1100, plot=False)
                pl_kws.update(pl_kwargs)
                plfit = analysis.photoluminescence.fit_spectrum(
                    wl=wl, cts=cps, **pl_kws
                )
                metrics[f"pl_intensity_{cidx}"] = plfit["intensity"]
                metrics[f"pl_peakev_{cidx}"] = plfit["peakev"]
                metrics[f"pl_fwhm_{cidx}"] = plfit["fwhm"]

        if photostability:
            psfid = os.path.join(chardir, f"{sample}_photostability.csv")
            if os.path.exists(psfid):
                time, wl, cps = analysis.photoluminescence.load_photostability(psfid)
                raw[f"ps_{cidx}"] = {
                    "time": time,
                    "wl": wl,
                    "cps": cps,
                }
                ps_kws = dict(wlmin=675, wlmax=1100, plot=False)
                ps_kws.update(ps_kwargs)
                psfit = analysis.photoluminescence.fit_photostability(
                    times=time, wl=wl, cts=cps, **ps_kws
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

        if transmission:
            tfid = os.path.join(chardir, f"{sample}_transmission.csv")
            if os.path.exists(tfid):
                wl, t = analysis.transmittance.load_spectrum(tfid)
                a = -np.log10(t)

                raw[f"t_{cidx}"] = {
                    "wl": wl,
                    "t": t,
                    "a": a,
                }
                t_kws = dict(
                    bandgap_type="direct",
                    wlmin=400,
                    wlmax=1050,
                    plot=False,
                )
                t_kws.update(t_kwargs)
                try:
                    metrics[f"t_bandgap_{cidx}"] = analysis.transmittance.tauc(
                        wl=wl,
                        a=a,
                        **t_kws,
                    )
                except:
                    metrics[f"t_bandgap_{cidx}"] = np.nan

                metrics[
                    f"t_samplepresent_{cidx}"
                ] = analysis.transmittance.sample_present(wl=wl, t=t)

        if darkfield:
            dffid = os.path.join(chardir, f"{sample}_darkfield.tif")
            df_kws = dict(red_only=False)
            df_kws.update(df_kwargs)
            if os.path.exists(dffid):
                img = analysis.darkfield.load_image(dffid, **df_kws)
                raw[f"df_{cidx}"] = img
                metrics[f"df_median_{cidx}"] = analysis.darkfield.get_median(
                    im=img[:, :, 0]
                )  # median counts on red channel

        if brightfield:
            bffid = os.path.join(chardir, f"{sample}_brightfield.tif")
            bf_kws = dict()
            bf_kws.update(bf_kwargs)
            if os.path.exists(bffid):
                img = analysis.brightfield.load_image(bffid)
                raw[f"bf_{cidx}"] = img
                metrics[
                    f"bf_inhomogeneity_{cidx}"
                ] = analysis.brightfield.inhomogeneity(img=img)

        if plimg:
            plimgfid = os.path.join(chardir, f"{sample}_plimage_5000ms.tif")
            plimg_kws = dict()
            plimg_kws.update(bf_kwargs)
            if os.path.exists(plimgfid):
                img = analysis.brightfield.load_image(plimgfid)
                raw[f"plimg_{cidx}"] = img

    return metrics, raw


def load_all(
    datadir: str,
    photoluminescence=True,
    photostability=True,
    transmission=True,
    brightfield=True,
    darkfield=True,
    pl_kwargs={},
    ps_kwargs={},
    t_kwargs={},
    bf_kwargs={},
    df_kwargs={},
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads + processes all characterization data, returns as DataFrame's

    Args:
        datadir (str): directory in which characterization data is stored

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: dataframe with all fitted metrics from acquired data, dataframe with all raw data
    """

    all_samples = [
        s for s in os.listdir(datadir) if os.path.isdir(os.path.join(datadir, s))
    ]
    all_samples = natsorted(all_samples)  # sort names
    all_metrics = {}
    all_raw = {}
    for s in tqdm(all_samples, desc="Loading data", unit="sample"):
        try:
            all_metrics[s], all_raw[s] = load_sample(
                sample=s,
                datadir=datadir,
                photoluminescence=photoluminescence,
                photostability=photostability,
                transmission=transmission,
                brightfield=brightfield,
                darkfield=darkfield,
                pl_kwargs=pl_kwargs,
                ps_kwargs=ps_kwargs,
                t_kwargs=t_kwargs,
                bf_kwargs=bf_kwargs,
                df_kwargs=df_kwargs,
            )
        except:
            tqdm.write(f"Could not load data for sample {s}")
    metric_df = pd.DataFrame(all_metrics).T
    metric_df["name"] = metric_df.index
    raw_df = pd.DataFrame(all_raw).T
    raw_df["name"] = raw_df.index
    return metric_df, raw_df


def get_worklist_times(fid, exclude_list=None):
    with open(fid, "r", encoding="utf-8") as f:
        log = json.loads(f.read())

    log_extract = {}

    for i in list(log.keys()):
        temp_worklist = []
        log_extract[i] = []
        for j in range(len(log[i]["worklist"])):
            temp_worklist.append(log[i]["worklist"][j]["name"])
            temp_dict = dict.fromkeys(temp_worklist, [])
            log_extract[i] = temp_dict

    # get finish_actual for each step
    for sample in log_extract.keys():
        for task in log_extract[sample].keys():
            spin_coat_index = 0
            for n in range(len(log[sample]["worklist"])):

                if log[sample]["worklist"][n]["name"] == task:
                    if spin_coat_index == 0:
                        log_extract[sample][task] = [
                            np.round(
                                log[sample]["worklist"][n]["finish_actual"] / 60, 2
                            )
                        ]
                    if task == "spincoat":
                        spin_coat_index += 1
                    if spin_coat_index > 1:
                        log_extract[sample][task].append(
                            np.round(
                                log[sample]["worklist"][n]["finish_actual"] / 60, 2
                            )
                        )

    if exclude_list is not None:
        exclude_list = list(exclude_list)
        for n in range(len(exclude_list)):
            exclude_list[n] = "sample" + str(exclude_list[n])
        for sample in exclude_list:
            if sample in log_extract.keys():
                log_extract.pop(sample)

    data = {}
    data["sample"] = []
    data["spincoat"] = []
    # data["spincoater_to_hotplate"] = []
    # data["anneal"] = []
    # data["hotplate_to_storage"] = []
    # data["rest"] = []
    # data["storage_to_characterization"] = []
    # data["characterize"] = []
    # data["characterization_to_storage"] = []

    for sample in log_extract.keys():
        data["sample"].append(sample)
        for task in log_extract[sample].keys():

            if task == "spincoat":
                data["spincoat"].append(log_extract[sample][task])
            # if task == "spincoater_to_hotplate":
            #     data["spincoater_to_hotplate"].append(log_extract[sample][task])
            # if task == "anneal":
            #     data["anneal"].append(log_extract[sample][task])
            # if task == "hotplate_to_storage":
            #     data["hotplate_to_storage"].append(log_extract[sample][task])
            # if task == "rest":
            #     data["rest"].append(log_extract[sample][task])
            # if task == "storage_to_characterization":
            #     data["storage_to_characterization"].append(log_extract[sample][task])
            # if task == "characterize":
            #     data["characterize"].append(log_extract[sample][task])
            # if task == "characterization_to_storage":
            #     data["characterization_to_storage"].append(log_extract[sample][task])

    df = pd.DataFrame(data)

    df["spincoat0"] = ""
    df["spincoat1"] = ""

    for n in range(df.shape[0]):
        if len(df["spincoat"][n]) == 1:
            df["spincoat0"][n] = [df["spincoat"][n][0]]
        if len(df["spincoat"][n]) == 2:
            df["spincoat0"][n] = [df["spincoat"][n][0]]
            df["spincoat1"][n] = [df["spincoat"][n][1]]

    df["name"] = ""
    for n in range(len(df)):

        df["name"][n] = df["sample"][n].split("e")[1]
    df[""] = df["name"].astype(int)
    df = df.set_index("")

    df = df.sort_index()

    return df


def compress_jv(jv_pkl_fid):
    df_jv = pd.read_pickle(jv_pkl_fid)

    df_jv = df_jv.rename(columns={"PASCAL_ID": "name"})

    df_jv["pce_f"] = None
    df_jv["pce_r"] = None
    df_jv["ff_f"] = None
    df_jv["ff_r"] = None
    df_jv["voc_f"] = None
    df_jv["voc_r"] = None
    df_jv["jsc_f"] = None
    df_jv["jsc_r"] = None

    for n in range(df_jv.shape[0]):
        if df_jv["direction"][n] == "fwd":
            df_jv["pce_f"][n] = df_jv["pce"][n]
            df_jv["ff_f"][n] = df_jv["ff"][n]
            df_jv["voc_f"][n] = df_jv["voc"][n]
            df_jv["jsc_f"][n] = df_jv["jsc"][n]

        if df_jv["direction"][n] == "rev":
            df_jv["pce_r"][n] = df_jv["pce"][n]
            df_jv["ff_r"][n] = df_jv["ff"][n]
            df_jv["voc_r"][n] = df_jv["voc"][n]
            df_jv["jsc_r"][n] = df_jv["jsc"][n]

    test = pd.DataFrame(
        columns=[
            "name",
            "pce_f",
            "pce_r",
            "ff_f",
            "ff_r",
            "voc_f",
            "voc_r",
            "jsc_f",
            "jsc_r",
        ]
    )
    test["name"] = list(df_jv["name"].unique())
    test[""] = test["name"]
    test = test.set_index("")

    for n in range(df_jv.shape[0]):
        if df_jv["direction"][n] == "fwd":
            test["pce_f"][df_jv["name"][n]] = df_jv["pce"][n]
            test["ff_f"][df_jv["name"][n]] = df_jv["ff"][n]
            test["voc_f"][df_jv["name"][n]] = df_jv["voc"][n]
            test["jsc_f"][df_jv["name"][n]] = df_jv["jsc"][n]

        if df_jv["direction"][n] == "rev":
            test["pce_r"][df_jv["name"][n]] = df_jv["pce"][n]
            test["ff_r"][df_jv["name"][n]] = df_jv["ff"][n]
            test["voc_r"][df_jv["name"][n]] = df_jv["voc"][n]
            test["jsc_r"][df_jv["name"][n]] = df_jv["jsc"][n]

    test = test.sort_index()
    return test
