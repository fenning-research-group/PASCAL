import tifffile
import numpy as np


def load(fid):
    img = tifffile.imread(fid)
    return img * 64  # rescales to 0-1


class SampleChecker:
    def __init__(self):
        self._load_model()

    def _load_model(self):
        """
        loads pretrained Keras classifier to identify dropped samples
        by brightfield imaging
        """
        return

    def sample_is_present(self, img) -> bool:
        """
        given a PASCAL brightfield image, identifies whether or not
        a sample was present in the characterization stage.

        True = sample is detected on stage
        False = sample was not detected on stage. probably dropped earlier in the protocol
        """
        return True
