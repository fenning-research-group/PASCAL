from tifffile import imread
import numpy as np
from frgpascal.analysis.curvehelpers import plane, fit_plane_to_image
import dill
import os

MODULE_DIR = os.path.dirname(__file__)

### brightfield image coordinates within the window of the characterization sample carrier
CENTER_SLICE_Y = slice(300, 780)
CENTER_SLICE_X = slice(400, 1040)


def load_image(fid):
    """
    Loads an image file from a given fid,
    then converts it from float64 to float32
    """
    img = imread(fid) * 64
    return img.astype(np.float32)


def inhomogeneity(img: np.ndarray) -> float:
    """
    Calculates the "inhomogeneity" of an RGB image. "Inhomogeneity" is taken as
    deviation from the best fit plane in R,G,B spaces.

    lower = better
    """
    flatnesses = []
    for color_index in range(img.shape[2]):
        img_to_fit = img[CENTER_SLICE_Y, CENTER_SLICE_X, color_index]
        plane_params = fit_plane_to_image(img_to_fit)
        delta = np.abs(img_to_fit - plane_params["plane"])
        flatnesses.append(np.mean(delta) + np.std(delta))
    return np.mean(flatnesses)
