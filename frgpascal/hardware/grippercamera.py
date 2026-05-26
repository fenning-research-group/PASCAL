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
        self.base_dir = None
        
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
        self._current_images = []
        self._raw_images = []
        self._current_meta = []

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
        # TODO: implement properly, for now assuming sample is always present
        return True

    # TODO: Implement sample detection
    def log_capture(self, image: np.ndarray, metadata: dict):
        """Adds a processed image, a raw image, and metadata to the current batch."""
        self._current_images.append(image)
        self._raw_images.append(image)  
        self._current_meta.append(metadata)


    def archive_production_batch(self):
        """Saves the current memory buffer to structured sample folders and clears it."""
        if len(self._current_images) == 0:
            return # Nothing to save

        if self.base_dir is None:
            print("base_dir is not set, skipping archive.")
            return

        for i in range(len(self._current_images)):
            img = self._current_images[i]
            meta = self._current_meta[i]

            sample_name = meta.get("sample", "unknown_sample")
            task_id = meta.get("task_id", f"unknown_task_{time.time()}")
            action = meta.get("action", "unknown_action")

            filename = f"{task_id}_{action}.png"

            # Ensure sample transfer directory exists
            sample_dir = os.path.join(self.base_dir, sample_name)
            transfers_dir = os.path.join(sample_dir, "transfers")
            os.makedirs(transfers_dir, exist_ok=True)

            # Convert RGB back to BGR for OpenCV saving
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # Save PNG
            cv2.imwrite(os.path.join(transfers_dir, filename), img_bgr)

            # Save Metadata to HDF5
            h5_path = os.path.join(sample_dir, f"{sample_name}.h5")
            with h5py.File(h5_path, 'a') as f:
                group_name = f"{task_id}_{action}"
                if group_name in f:
                    grp = f[group_name]
                else:
                    grp = f.create_group(group_name)
                
                for k, v in meta.items():
                    grp.attrs[k] = v

        print(f"Batch {self.batch_id} saved to {self.base_dir}")

        # Reset memory
        self._current_images = []
        self._raw_images = []
        self._current_meta = []
        self.batch_id += 1