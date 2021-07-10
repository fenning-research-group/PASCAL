import numpy as np
import itertools
import random

#### name parsing helper functions


def components_to_name(components, delimiter="_"):
    composition_label = ""
    for c, n in components.items():
        if n > 0:
            composition_label += "{0}{1:.2f}{2}".format(c, n, delimiter)

    return composition_label[:-1]


def name_to_components(
    name,
    factor=1,
    delimiter="_",
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
        components[species] = count * factor
    return components


#### individual solution functions


def get_components(
    name,
    factor=1,
    delimiter="_",
):
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