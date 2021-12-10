import tifffile
import numpy as np


def load(fid):
    img = tifffile.imread(fid)
    return img * 64  # rescales to 0-1


def bright_fraction(img):
    THRESHOLD = 0.2
    return np.sum(img > THRESHOLD) / np.product(img.shape)
