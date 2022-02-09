from tifffile import imread
import numpy as np
from frgpascal.analysis.curvehelpers import plane, fit_plane_to_image
import dill
import os

# try:
#     from tensorflow.keras.models import load_model
#     from tensorflow.image import resize

#     TENSORFLOW_AVAILABLE = True
# except ImportError:
TENSORFLOW_AVAILABLE = False

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
        plane_params = fit_plane_to_image(
            img[CENTER_SLICE_Y, CENTER_SLICE_X, color_index]
        )
        delta = np.abs(img - plane_params["plane"])
        flatnesses.append(np.mean(delta) + np.std(delta))
    return np.mean(flatnesses)


class SampleChecker:
    def __init__(self):
        self.THRESHOLD = 0.5
        if TENSORFLOW_AVAILABLE:
            self._load_model()
            self.__model_loaded = True
        else:
            self.__model_loaded = False
            print(
                "Tensorflow not available, SampleChecker will assume True (ie all samples considered valid)"
            )

    def _load_model(self):
        """
        loads pretrained Keras binary classifier and ImageDataGenerator to identify dropped samples
        by brightfield imaging
        """
        self.model = load_model(
            os.path.join(MODULE_DIR, "assets", "Brightfield_SampleChecker_Model.h5")
        )

        with open(
            os.path.join(MODULE_DIR, "assets", "Brightfield_SampleChecker_datagen.pkl"),
            "rb",
        ) as f:
            self.datagen = dill.load(f)

    def sample_is_present_fromfile(self, fpath, return_probability=False) -> bool:
        """
        given the filepath to a PASCAL brightfield image, identifies whether or not
        a sample was present in the characterization stage.

        True = sample is detected on stage, >=0.5 probability
        False = sample was not detected on stage. probably dropped earlier in the protocol, <0.5 probability
        """

        img = load_image(fpath)
        return self.sample_is_present(img=img, return_probability=return_probability)

    def sample_is_present(self, img, return_probability=False) -> bool:
        """
        given a PASCAL brightfield image, identifies whether or not
        a sample was present in the characterization stage.

        True = sample is detected on stage, >=0.5 probability
        False = sample was not detected on stage. probably dropped earlier in the protocol, <0.5 probability
        """
        # use the ImageDataGenerator to preprocess the image
        if not self.__model_loaded:
            return True
        img1 = self.datagen.standardize(img)
        # resize image to match model input
        img1 = resize(img1, [200, 200])
        img1 = np.expand_dims(img1, axis=0)
        # predict the probability of sample being present
        ans = self.model.predict(img1)
        # return bool and the probability
        if return_probability:
            response = (ans[0][0] > self.THRESHOLD, ans[0][0])
        else:
            response = ans[0][0] > self.THRESHOLD

        return response
