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
        
        # Load sample detection SVM model if it exists
        self.model_path = os.path.join(MODULE_DIR, "calibrations", "sample_detection_model.xml")
        self.svm = None
        if os.path.exists(self.model_path):
            self.svm = cv2.ml.SVM_load(self.model_path)

        
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

        # Flush the internal camera buffer to avoid capturing stale frames from previous transfers
        for _ in range(5):
            self.handle.grab()

        ret, frame = self.handle.read()
        if not ret:
            raise RuntimeError("Can't receive frame (stream end?).")

        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def _extract_features(self, img: np.ndarray) -> np.ndarray:
        """Crops the central Region of Interest and extracts HOG features."""
        # Convert to grayscale if needed
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
            
        # Crop to Region of Interest (the space between the claws)
        h, w = gray.shape
        roi = gray[int(h*0.3):int(h*0.7), int(w*0.3):int(w*0.7)]
        roi = cv2.resize(roi, (64, 64))
        
        # HOG descriptor
        hog = cv2.HOGDescriptor(
            _winSize=(64,64),
            _blockSize=(16,16),
            _blockStride=(8,8),
            _cellSize=(8,8),
            _nbins=9
        )
        features = hog.compute(roi)
        return features.flatten()

    def train_model(self, data_dir: str):
        """
        Parses gripper_camera_pictures directory to auto-label and train an SVM.
        """
        import glob
        print(f"Training SVM from dataset in {data_dir}...")
        features_list = []
        labels_list = []
        
        search_path = os.path.join(data_dir, "**", "transfers", "*.png")
        image_paths = glob.glob(search_path, recursive=True)
        
        for path in image_paths:
            filename = os.path.basename(path)
            # Auto-label based on filename
            if "catch" in filename:
                label = 1
            elif "release" in filename:
                label = 0
            else:
                continue
                
            img = cv2.imread(path)
            if img is None:
                continue
                
            feats = self._extract_features(img)
            features_list.append(feats)
            labels_list.append(label)
            
        if not features_list:
            print("No training data found!")
            return
            
        features_np = np.array(features_list, dtype=np.float32)
        labels_np = np.array(labels_list, dtype=np.int32)
        
        svm = cv2.ml.SVM_create()
        svm.setType(cv2.ml.SVM_C_SVC)
        svm.setKernel(cv2.ml.SVM_LINEAR)
        svm.setTermCriteria((cv2.TERM_CRITERIA_MAX_ITER, 1000, 1e-6))
        
        print(f"Training on {len(labels_list)} images...")
        svm.train(features_np, cv2.ml.ROW_SAMPLE, labels_np)
        
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        svm.save(self.model_path)
        self.svm = svm
        print(f"Model successfully saved to {self.model_path}")

    def detect_sample(self, img: np.ndarray) -> bool:
        """
        Evaluates an image to detect if a square glass substrate is present between the claws.
        Returns True if found, False otherwise.
        """
        if self.svm is None:
            print("Warning: Sample detection SVM not loaded. Run train_model() first. Defaulting to True.")
            return True
            
        features = self._extract_features(img)
        features = np.array([features], dtype=np.float32)
        _, result = self.svm.predict(features)
        
        return bool(result[0][0] == 1)

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