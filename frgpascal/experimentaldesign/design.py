import numpy as np
import itertools
import random
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import json
from natsort import index_natsorted
from sklearn.decomposition import NMF
from scipy.optimize import nnls

#### name parsing helper functions
def components_to_name(components: dict, delimiter="_") -> str:
    composition_label = ""
    for c, n in components.items():
        if n == 1:
            composition_label += "{0}{1}".format(c, delimiter)
        elif n > 0:
            nstr = f"{n:.3f}".rstrip("0").rstrip(".")
            composition_label += "{0}{1}{2}".format(c, nstr, delimiter)

    return composition_label[:-1]


def name_to_components(name, factor=1, delimiter="_") -> dict:
    """Converts composition string to dictionary
        example: "MA_Pb0.5_Sn0.5_I3" -> {"MA":1, "Pb":0.5, "Sn":0.5, "I":3}

    Args:
        name (str): delimited string of composition
        factor (int, optional): factor by which to scale all component amounts. Defaults to 1.
        delimiter (str, optional): Defaults to "_".

    Returns:
        [dict]: Dictionary with key:value = component:amount
    """
    components = {}
    for part in name.split(delimiter):
        species = part
        count = 1.0
        for l in range(len(part), 0, -1):
            try:
                count = float(part[-l:])
                species = part[:-l]
                break
            except:
                pass
        components[species] = count * factor
    return components


#### individual solution functions

# REFACTOR #5 get_components and name_to_components are the same function!
def get_components(
    name,
    factor=1,
    delimiter="_",
) -> dict:
    """Converts composition string to dictionary
        example: "MA_Pb0.5_Sn0.5_I3" -> {"MA":1, "Pb":0.5, "Sn":0.5, "I":3}

    Args:
        name (str): delimited string of composition
        factor (int, optional): factor by which to scale all component amounts. Defaults to 1.
        delimiter (str, optional): Defaults to "_".

    Returns:
        [dict]: Dictionary with key:value = component:amount
    """
    return name_to_components(name, factor, delimiter)


def get_solvent(name):
    """
    normalize solvent volumes -> solvent fractions
    """
    solvent_dict = get_components(name)
    total = np.sum(list(solvent_dict.values()))
    return {solvent: amt / total for solvent, amt in solvent_dict.items()}


#### combining functions to generate experiment mesh


def compositions_spread(compositions, interp):
    interp += 1
    if interp <= 0:
        raise ValueError("interp must be > 0!")

    # load all unique components in spread,
    composition_components = [name_to_components(s) for s in compositions]
    components = []
    for s in composition_components:
        components += list(s.keys())
    components = np.unique(components)

    # sort by average order in endpoints (try to follow user convention for composition naming)
    component_order = np.full((len(components), len(composition_components)), np.nan)
    for n, s in enumerate(composition_components):
        for i, c in enumerate(s):
            m = np.where(components == c)[0]
            component_order[m, n] = i
    avg_order = np.argsort(np.nanmean(component_order, axis=1))
    components = components[avg_order]

    # generate component matrix to interpolate between
    mat = np.zeros((len(compositions), len(components)))
    for sidx, s in enumerate(composition_components):
        for cidx, c in enumerate(components):
            if c in s:
                mat[sidx, cidx] = s[c]

    compositions = []
    for mix in itertools.combinations_with_replacement(mat, interp):
        composition_amounts = np.array(mix).mean(axis=0)
        components_dict = {c: a for c, a in zip(components, composition_amounts)}
        compositions.append(
            components_to_name(components_dict)
        )  # exclude the last underscore

    return list(np.unique(compositions))


# Well Plate Handling
def well_list_generator(nrows=12, ncols=8, random=False):
    if not random:
        num = 0
        col = -1
        while num < nrows * ncols:
            row = num % nrows
            if row == 0:
                col += 1
            yield f"{str.upper(chr(col+97))}{row+1}"
            num += 1
    else:
        wells = []
        num = 0
        col = -1
        while num < nrows * ncols:
            row = num % nrows
            if row == 0:
                col += 1
            wells.append(f"{str.upper(chr(col+97))}{row+1}")
            num += 1

        idx = np.arange(nrows * ncols)
        np.random.shuffle(idx)

        for idx_ in idx:
            yield (wells[idx_])


def generate_sample_list(
    compositions,
    solvents,
    molarities,
    volumes,
    randomize=True,
    repeats=3,
    nrows=12,
    ncols=8,
):
    samples = []
    plates = []
    well_generator = well_list_generator(nrows=nrows, ncols=ncols, random=randomize)

    for c, s, m, v in itertools.product(compositions, solvents, molarities, volumes):
        for r in range(repeats):
            try:
                this_well = next(well_generator)
            except:
                raise Exception("Too many samples, well can only hold up to 96!")
            samples.append(
                dict(composition=c, solvent=s, molarity=m, volume=v, well=this_well)
            )
    if randomize:
        random.shuffle(samples)
    return samples


def generate_composition_columns(df):
    components = set()
    for _, r in df.iterrows():
        for c in name_to_components(r["composition"]):
            components.add(c)
    dfData = {c: [] for c in components}
    for _, r in df.iterrows():
        this_components = name_to_components(r["composition"])
        for c in components:
            dfData[c].append(this_components.get(c, 0))
    df2 = pd.DataFrame(dfData)
    df = df.join(df2)
    return df


# stock solution + mixture calculators


def calculate_mix(
    target, target_solvent, volume, molarity, solution_sources, min_volume=10e-6
):
    # find unique solution components present in stock solutions
    solutes = set(
        [
            c
            for stk in solution_sources
            for c in name_to_components(stk)
            if "Solvent" not in stk
        ]
    )
    solvents = set(
        [
            c
            for vals in solution_sources.values()
            for c in name_to_components(vals["solvent"])
        ]
    )

    ### Construct stock + target matrices
    row_key = {}
    i = 0
    for s in solutes:
        row_key[s] = i
        i += 1
    for s in solvents:
        row_key[s] = i
        i += 1

    stock_matrix = np.zeros((len(row_key), len(solution_sources)))
    wells = []
    for n, (name, vals) in enumerate(solution_sources.items()):
        wells.append(vals["well"])
        for solute, amt in get_components(name).items():
            if "Solvent" in solute:
                continue
            m = row_key[solute]
            stock_matrix[m, n] = amt * vals["molarity"]
        for solvent, amt in get_solvent(vals["solvent"]).items():
            m = row_key[solvent]
            stock_matrix[m, n] = amt

    target_matrix = np.zeros((len(row_key)))
    for solute, amt in get_components(target).items():
        if "Solvent" in solute:
            continue
        try:
            m = row_key[solute]
        except:
            raise Exception(f"{solute} not present in your stock solutions!")
        target_matrix[m] = amt * molarity * volume
    for solvent, amt in get_solvent(target_solvent).items():
        try:
            m = row_key[solvent]
        except:
            raise Exception(f"{solvent} not present in your stock solutions!")
        target_matrix[m] = amt * volume

    # amount_matrix, *data = np.linalg.lstsq(stock_matrix*1e6, target_matrix*1e6, rcond = None) #volumes to mix. math is better if not such small values in matrix, so scale to uL for calculation
    amount_matrix, *data = nnls(
        stock_matrix, target_matrix, maxiter=1e3
    )  # volumes to mix. math is better if not such small values in matrix, so scale to uL for calculation
    amount_matrix[
        amount_matrix < 1e-6
    ] = 0  # clean up values that are essentially 0. If we have a significant negative value here, should get caught downstream
    amount_matrix = np.round(
        amount_matrix, 6
    )  # round to nearest uL (values are in L at this point)

    doublecheck = stock_matrix @ amount_matrix
    composition_error = max(
        [np.abs(1 - c / t) for c, t in zip(doublecheck, target_matrix) if t > 0]
    )

    if (
        composition_error < 0.05
    ):  # check that we are within 5% error wrt target composition AT EACH SITE
        results = {}
        for well, solution_volume in zip(wells, amount_matrix):
            results[well] = solution_volume  # round to nearest uL
    else:
        results = False
        target_achieved = components_to_name(
            {
                c: amt / molarity / volume
                for c, amt in zip(row_key, doublecheck)
                if amt > 0
            }
        )

        raise Exception(
            f"Unable to generate target solution ({volume*1e6} uL of {molarity}M {target} in"
            f"{target_solvent}) with current stock solutions.\n\n"
            f"Closest match is {target_achieved} - max site error of {composition_error*100:.2f}%"
        )  # {Off by {composition_error*100:.2f}%%')

    # if amount_matrix.sum() > volume:
    #     raise Exception(f'Volume Overflow ({amount_matrix.sum()/volume})')
    return results


def name_to_cvector(composition, components):
    cvector = []
    thesecomponents = name_to_components(composition)
    for c in components:
        cvector.append(thesecomponents.get(c, 0))
    return np.array(cvector)


def suggest_solutions(
    compositions,
    normalization_components=None,
    normalization_value=1,
    tol=0.001,
    roundto=2,
    verbose=False,
):
    components = list(
        set([c for comp in compositions for c in name_to_components(comp)])
    )  # set of unique components in target compositions
    target_matrix = np.stack(
        [name_to_cvector(comp, components) for comp in compositions]
    )  # num_compositions x num_components matrix of target compositions

    n_solutions = 1
    err = np.inf
    while err > tol:
        n_solutions += 1
        nmf = NMF(
            n_components=n_solutions,
            max_iter=int(1e6),
            tol=1e-10,
        )
        nmf.fit(target_matrix)
        err = nmf.reconstruction_err_

    weights = nmf.components_
    if normalization_components is not None:
        normidx = [c in normalization_components for c in components]
        normweight = normalization_value / weights[:, normidx].sum(axis=1).reshape(
            -1, 1
        )
        weights *= normweight
    weights = np.round(weights, roundto)
    solutions = [
        components_to_name({c: a for c, a in zip(components, w)}) for w in weights
    ]
    nmf.components_ = weights
    amounts = nmf.transform(target_matrix)
    if verbose:
        actual = amts @ weights
        pct_off = (actual / target - 1) * 100
        pct_off[~np.isfinite(pct_off)] = 0  # if divide by zero error
        errordf = pd.DataFrame(pct_off, columns=components)
        sns.histplot(data=errordf)
        plt.xlabel("Percent Error for Any Single Component/Composition")
    return solutions