import numpy as np
import itertools
from frgpascal.experimentaldesign.recipes import (
    SolutionRecipe,
    Sample,
)
from scipy.optimize import nnls
from copy import deepcopy
import uuid


#### General
def generate_unique_id():
    return str(uuid.uuid4())


#### name parsing helper functions
def components_to_name(components, delimiter="_"):
    composition_label = ""
    for c, n in components.items():
        if n > 0:
            composition_label += "{0}{1:.2f}{2}".format(c, n, delimiter)

    return composition_label[:-1]


def name_to_components(
    name, factor=1, delimiter="_",
):
    """
        given a chemical formula, returns dictionary with individual components/amounts
        expected name format = 'MA0.5_FA0.5_Pb1_I2_Br1'.
        would return dictionary with keys ['MA, FA', 'Pb', 'I', 'Br'] and values [0.5,.05,1,2,1]*factor
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
        if species == "":
            continue
        components[species] = count * factor
    return components


#### stock solution management


def where_to_store(volume, options):
    for ll in options:
        if volume <= ll.volume and len(ll._openslots) > 0:
            return ll
    raise ValueError(f"No options have enough space to hold {volume/1e3:.2f} mL!")


# def suggest_stock_solutions(target_solutions):
#     """
#     suggests smallest number of stock solutions required to cover the
#     target solution space
#     """

#     return


def calculate_mix(
    target: SolutionRecipe,
    volume: float,
    stock_solutions: list,
    tolerance: float = 0.05,
):
    """
    given a target solution, target volume, and list of stock solutions, calculates
    the volumes needed from individual stocks to achieve target composition

    tolerance (float): maximum error for single site (relative, not absolute) allowed.
    
    """
    # get possible solution components from stock list
    components = set()
    for s in stock_solutions:
        components.update(s.solute_dict.keys(), s.solvent_dict.keys())
    components = list(
        components
    )  # sets are not order-preserving, lists are - just safer this way

    # organize components into a stock matrix, keep track of which rows are solvents
    stock_matrix = np.zeros((len(components), len(stock_solutions)))
    solvent_idx = set()
    for n, s in enumerate(stock_solutions):
        for m, c in enumerate(components):
            if c in s.solute_dict:
                stock_matrix[m, n] = s.solute_dict[c] * s.molarity
            elif c in s.solvent_dict:
                stock_matrix[m, n] = s.solvent_dict[c]
                solvent_idx.add(m)
    solvent_idx = list(solvent_idx)

    # organize target solution into a matrix of total mols desired of each component
    target_matrix = np.zeros((len(components),))
    for m, c in enumerate(components):
        if c in target.solute_dict:
            target_matrix[m] = target.solute_dict[c] * target.molarity * volume
        elif c in target.solvent_dict:
            target_matrix[m] = target.solvent_dict[c] * volume

    # solve for the mixture amounts
    amount_matrix, *data = nnls(
        stock_matrix, target_matrix, maxiter=1e3
    )  # volumes to mix. math is better if not such small values in matrix, so scale to uL for calculation
    amount_matrix[
        amount_matrix < 1
    ] = 0  # clean up values that are essentially 0. If we have a significant negative value here, should get caught downstream
    amount_matrix = np.round(
        amount_matrix
    )  # round to nearest uL (values are in L at this point)

    # double check that the solved amounts make sense
    doublecheck = stock_matrix @ amount_matrix
    doublecheck[solvent_idx] /= (
        doublecheck[solvent_idx].sum() / volume
    )  # solvents should sum to one
    # print(stock_matrix)
    # print(amount_matrix)
    # print(target_matrix)
    composition_error = max(
        [np.abs(1 - c / t) for c, t in zip(doublecheck, target_matrix) if t > 0]
    )  # max single-component error fraction

    if (
        composition_error < tolerance
    ):  # check that we are within error tolerance wrt target composition AT EACH SOLUTE/SOLVENT SPECIES
        return amount_matrix
    else:
        solute = components_to_name(
            {
                c: amt / target.molarity / volume
                for c, amt in zip(components, doublecheck)
                if amt > 0 and c not in target.solvent_dict
            }
        )
        solvent = components_to_name(
            {
                c: amt / target.molarity / volume
                for c, amt in zip(components, doublecheck)
                if amt > 0 and c in target.solvent_dict
            }
        )
        # print(solvent)
        raise Exception(
            f"Unable to generate target solution ({volume} uL of {target}) with current stock solutions.\n\n"
            f"Closest match ({volume} uL of {target.molarity}M {solute} in {solvent}) has a max site error of {composition_error*100:.2f}%"
        )  # {Off by {composition_error*100:.2f}%%')


#### Construct sample list from experimental mesh


def build_sample_list(
    available_trays,
    input_substrates,
    target_solutions,
    spincoat_recipes,
    anneal_recipes,
    n_repeats=1,
    ignore_storage=False,
):
    """
    Permutes experimental mesh into sample list
    """
    sample_list = []
    for tray in available_trays:
        tray.unload_all()
    trays = iter(available_trays)
    current_tray = next(trays)

    def get_storage_slot(name, current_tray, trays):
        loaded = False
        while not loaded:
            try:
                slot = current_tray.load(name)
                loaded = True
            except:
                try:
                    current_tray = next(trays)
                except StopIteration:
                    raise StopIteration(
                        "No more slots available in your storage trays!"
                    )
        return {"tray": current_tray.name, "slot": slot}, current_tray, trays

    idx = 0
    for sub, sol, sc, an in itertools.product(
        input_substrates, target_solutions, spincoat_recipes, anneal_recipes
    ):
        # recipe_id = generate_unique_id()
        sc_ = deepcopy(sc)
        sc_.solution = sol
        for r in range(n_repeats):
            name = f"sample{idx}"
            idx += 1
            if ignore_storage:
                storage_slot = None
            else:
                storage_slot, current_tray, trays = get_storage_slot(
                    name, current_tray, trays
                )
            sample_list.append(
                Sample(
                    name=name,
                    substrate=sub,
                    spincoat_recipe=sc_,
                    anneal_recipe=an,
                    storage_slot=storage_slot
                    # sampleid=sampleid
                )
            )

    return sample_list
