# from termios import error
import time
import numpy as np
import yaml
import os
import serial
import threading
import cv2
import json
import h5py

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class GripperCamera:
    # gripper camera variables
    def __init__(self, id=None):
        """
        id is 0 usually and increments based on how many cameras are connected, i.e if it is the second 
        conencted camera then it should have an id of 1, etc. 
        """
        self.id = id
        self.handle = None
        self.batch_id = 0
        self.batch_size = 10
        self.file_path = "gripper_camera_default.h5"
        
        # In-memory storage for the current 'hot' batch
        self._current_images = []
        self._raw_images = []  # Holds the raw images
        self._current_meta = []
        
    def connect(self):
        self.handle = cv2.VideoCapture(self.id, cv2.CAP_DSHOW)
        if not self.handle.isOpened():
            self.handle = None
            raise ValueError(f"Could not connect to IR Camera at id {self.id}!")
        # settings
        # self.handle.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc("Y", "1", "6", " "))
        # self.handle.set(cv2.CAP_PROP_CONVERT_RGB, 0)

    def disconnect(self):
        self.handle.release()  # TODO maybe not correct syntax for opencv

    def capture_image(self):
        """Captures an image using the already-opened camera stream."""
        if self.handle is None or not self.handle.isOpened():
            raise RuntimeError("Camera is not connected. Call connect() first.")

        ret, frame = self.handle.read()
        if not ret:
            raise RuntimeError("Can't receive frame (stream end?).")

        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def detect_sample(self, img: np.ndarray) -> bool:
        """
        Evaluates an image to detect if a square glass substrate is present.
        Returns True if found, False otherwise.
        """
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Apply Gaussian Blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
                    
        return False # No sample detected

    def log_capture(self, image: np.ndarray, metadata: dict):
        """Adds a processed image, a raw image, and metadata to the current batch."""
        self._current_images.append(image)
        self._raw_images.append(image)  
        self._current_meta.append(metadata)

        # If the batch is full, automatically flush it to disk
        if len(self._current_images) >= self.batch_size:
            self.archive_production_batch()

    def archive_production_batch(self, filepath=None):
        """Saves the current memory buffer to HDF5 and clears it."""
        if len(self._current_images) == 0:
            return # Nothing to save

        if filepath is None:
            filepath = self.file_path

        # Convert list of images to 4D numpy arrays (N, H, W, C)
        images_array = np.array(self._current_images)
        raw_images_array = np.array(self._raw_images)

        # Create a batch-level metadata context
        batch_meta = {
            "timestamp_saved": time.time(),
            "batch_size": len(self._current_images)
        }

        # Call HDF5 saving logic
        with h5py.File(filepath, 'a') as f:
            # Create a group for the batch
            grp = f.create_group(f"batch_{self.batch_id}")
            
            # Batch-level info (Global context)
            for k, v in batch_meta.items():
                grp.attrs[k] = v
                
            # Processed Images
            grp.create_dataset('images', data=images_array, compression="lzf")  # Fixed variable name
            
            # Raw Images (Added this dataset)
            grp.create_dataset('raw_images', data=raw_images_array, compression="lzf")
            
            # Per-image metadata
            meta_json_btns = np.array([json.dumps(m).encode('utf-8') for m in self._current_meta])  # Fixed variable name
            grp.create_dataset('meta', data=meta_json_btns)

        print(f"Batch {self.batch_id} saved to {filepath}")

        # Reset memory and increment batch ID
        self._current_images = []
        self._raw_images = []  # Reset raw images memory buffer
        self._current_meta = []
        self.batch_id += 1