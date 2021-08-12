import cv2
import numpy as np


class FLIRLeptonPT2:
    def __init__(self, id=1):
        self.id = id
        self.connect()

    def connect(self):
        self.handle = cv2.VideoCapture(self.id, cv2.CAP_DSHOW)
        if not self.handle.isOpened():
            self.handle = None
            raise ValueError(f"Could not connect to IR Camera at id {self.id}!")
        self.handle.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc("Y", "1", "6", " "))
        self.handle.set(cv2.CAP_PROP_CONVERT_RGB, 0)

    def disconnect(self):
        self.handle.release()  # TODO maybe not correct syntax for opencv

    def __counts_to_celsius(self, cts):
        return cts / 100 - 273.15  # from centikelvin (camera output units) to Celsius

    def capture(self):
        """Captures a single shot infrared image. Data returned in Celsius

        Returns:
            np.array: Temperature image (Celsius)
        """
        self.handle.read()  # dummy frame, buffer is weird
        rval, frame = self.handle.read()  # actual frame
        if rval:
            frame = frame[:-2, :]
            return self.__counts_to_celsius(frame)
        else:
            return np.nan

    # def preview(self):
    #     if self.handle.isOpened(): # try to get the first frame
    #         rval, frame = video.read()
    #     else:
    #         rval = False

    #     while rval:
    #         normed = cv2.normalize(frame, None, 0, 65535, cv2.NORM_MINMAX)

    #         nor=cv2.cvtColor(np.uint8(normed),cv2.COLOR_GRAY2BGR)
    #         cv2.imshow(“preview”, cv2.resize(nor, dsize= (640, 480), interpolation = cv2.INTER_LINEAR))

    #         key = cv2.waitKey(1)
    #         if key == 27: # exit on ESC
    #             break
