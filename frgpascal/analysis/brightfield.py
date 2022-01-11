from tifffile import imread as ir
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.image import resize as rz
import dill
import os

MODULE_DIR = os.path.dirname(__file__)

def load(fid):
    """
    Loads an image file from a given fid,
    then converts it from float64 to float32
    """
    img = ir(fid)*64*255
    return img.astype(np.float32)


class SampleChecker:
    def __init__(self):
        self.THRESHOLD = 0.5
        self._load_model()

    def _load_model(self):
        """
        loads pretrained Keras binary classifier and ImageDataGenerator to identify dropped samples
        by brightfield imaging
        """
        self.model = load_model(os.path.join(MODULE_DIR, "datafiles", "MissingPresent_Model.h5"))
        
        with open(
            os.path.join(MODULE_DIR, "datafiles", "datagen.pkl"), "rb"
        ) as f:
            self.datagen = dill.load(f)  
        )
        
    def sample_is_present(self, img) -> bool:
        """
        given a PASCAL brightfield image, identifies whether or not
        a sample was present in the characterization stage.

        True = sample is detected on stage, >0.5 probability
        False = sample was not detected on stage. probably dropped earlier in the protocol, <0.5 probability
        """
        # use the ImageDataGenerator to preprocess the image
        img  = self.datagen.standardize(img)
        # resize image to match model input
        img = rz(img, [200, 200])
        img = np.expand_dims(img, axis=0)
        # predict the probability of sample being present
        ans = self.model.predict(img)
        # return bool and the probability
        if ans[0][0] > self.THRESHOLD:
            return True, ans[0][0]
        else:
            return False, ans[0][0]
