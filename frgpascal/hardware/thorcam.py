# try:
#     # if on Windows, use the provided setup script to add the DLLs folder to the PATH
#     from windows_setup import configure_path
#     configure_path()
# except ImportError:
#     configure_path = None
from thorlabs_tsi_sdk.tl_camera import TLCameraSDK
from thorlabs_tsi_sdk.tl_mono_to_color_processor import MonoToColorProcessorSDK
from thorlabs_tsi_sdk.tl_mono_to_color_enums import COLOR_SPACE
from thorlabs_tsi_sdk.tl_color_enums import FORMAT
from thorlabs_tsi_sdk.tl_camera_enums import SENSOR_TYPE

import numpy as np

"""
    The MonoToColorProcessorSDK and MonoToColorProcessor objects can be used with context managers for automatic 
    clean up. This multi-context-manager 'with' statement opens both the camera sdk and the mono to color sdk at 
    once. 
"""

class ThorcamHost:
    def __init__(self):
        self.camera_sdk = TLCameraSDK()
        self.discover_cameras()
        self.mono2color_sdk = MonoToColorProcessorSDK()

    def discover_cameras(self):
        self.available_cameras = self.camera_sdk.discover_available_cameras()
        if len(self.available_cameras) < 1:
            raise ValueError("no cameras detected")

    def spawn_camera(self, camid=None):
        if camid is None:
            if len(self.available_cameras) == 1:
                camid = self.available_cameras[0]
            else:
                camid = self.__user_select_camera()
        return Thorcam(camid, host=self)

    def __user_select_camera(self):
        print("Select camera:")
        for i, sn in enumerate(self.available_cameras):
            print(f"\t{i}: {sn}")
        selection = int(input("Enter index of camera you want: "))
        if selection >= len(self.available_cameras):
            raise ValueError(
                f"Index {selection} is out of range (0-{len(self.available_cameras)})!"
            )
        return self.available_cameras[selection]


class Thorcam:
    def __init__(self, id, host, color=True):
        self.__id = id
        self.__host = host
        self.color = color  # can set to false to get monochrome images
        self.connect()

    def connect(self):
        self.camera = self.__host.camera_sdk.open_camera(self.__id)
        self.camera.image_poll_timeout_ms = 1000  # 1 second polling timeout
        self.__image_width = self.camera.image_width_pixels
        self.__image_height = self.camera.image_height_pixels
        self.__mono2color_params = (
            self.camera.camera_sensor_type,
            self.camera.color_filter_array_phase,
            self.camera.get_color_correction_matrix(),
            self.camera.get_default_white_balance_matrix(),
            self.camera.bit_depth,
        )
        self.frames = 1
        
    @property
    def exposure(self):
        return self.camera.exposure_time_us

    @exposure.setter
    def exposure(self, exposure: int):
        """
        Args:
            exposure (int): Exposure time (microseconds)
        """
        self.camera.exposure_time_us = exposure

    @property
    def frames(self):
        self.__frames = self.camera.frames_per_trigger_zero_for_unlimited
        return self.__frames

    @frames.setter
    def frames(self, frames: int):
        """Set the number of frames to average per image capture

        Args:
            frames (int): number of frames to average
        """
        if frames == 0:
            raise ValueError("Frames must be >0!")
        self.camera.frames_per_trigger_zero_for_unlimited = frames
        self.__frames = frames

    def capture(self):
        self.camera.arm(self.__frames)
        self.camera.issue_software_trigger()
        frames = np.stack(
            [
                self.camera.get_pending_frame_or_null().image_buffer
                for f in range(self.__frames)
            ]
        )  # currently throwing away timing info
        self.camera.disarm()

        if self.color:
            with self.__host.mono2color_sdk.create_mono_to_color_processor(
                *self.__mono2color_params
            ) as mono_to_color_processor:
                """
                Once it is created, we can change the color space and output format properties. sRGB is the default
                color space, and will usually give the best looking image. The output format will determine how the
                transform image data will be structured.
                """
                mono_to_color_processor.color_space = (
                    COLOR_SPACE.SRGB
                )  # sRGB color space
                mono_to_color_processor.output_format = (
                    FORMAT.RGB_PIXEL
                )  # data is returned as sequential RGB values
                """
                    We can also adjust the Red, Green, and Blue gains. These values amplify the intensity of their 
                    corresponding colors in the transformed image. For example, if Blue and Green gains are set to 0 
                    and the Red gain is 10, the resulting image will look entirely Red. The most common use case for these 
                    properties will be for white balancing. By default they are set to model-specific values that gives 
                    reasonably good white balance in typical lighting.
                """
                # print(
                #     "Red Gain = {red_gain}\nGreen Gain = {green_gain}\nBlue Gain = {blue_gain}\n".format(
                #         red_gain=mono_to_color_processor.red_gain,
                #         green_gain=mono_to_color_processor.green_gain,
                #         blue_gain=mono_to_color_processor.blue_gain,
                #     )
                # )
                """
                    When we have all the settings we want for the mono to color processor, we call one of the transform_to 
                    functions to get a color image. 
                """
                # this will give us a resulting image with 3 channels (RGB) and 16 bits per channel, resulting in 48 bpp
                frames = np.stack(
                    [
                        mono_to_color_processor.transform_to_48(  # 48, 32, 24
                            f, self.__image_width, self.__image_height
                        ).reshape(self.__image_height, self.__image_width, 3)
                        for f in frames
                    ]
                )
        if self.__frames > 1:  ##this may be redundant
            averaged_image = frames.mean(axis=0)
        else:
            averaged_image = frames[0]


        averaged_image = averaged_image/(2**16) #normalize 16 bit depth to 0-1
        return averaged_image

    def preview(self):
        # create generic Tk App with just a LiveViewCanvas widget
        print("Generating app...")
        root = tk.Tk()
        root.title(self.camera.name)
        image_acquisition_thread = ImageAcquisitionThread(self)
        camera_widget = LiveViewCanvas(
            parent=root, image_queue=image_acquisition_thread.get_output_queue()
        )

        print("Setting camera parameters...")
        self.camera.frames_per_trigger_zero_for_unlimited = 0
        self.camera.arm(2)
        self.camera.issue_software_trigger()

        print("Starting image acquisition thread...")
        image_acquisition_thread.start()

        print("App starting")
        root.mainloop()

        print("Waiting for image acquisition thread to finish...")
        image_acquisition_thread.stop()
        image_acquisition_thread.join()

        print("Closing resources...")
        self.camera.disarm()
        self.camera.frames_per_trigger_zero_for_unlimited = self.__frames # put frames back to normal
        self.camera.image_poll_timeout_ms = 1000  # back to default


### Camera Preview Code from Thorlabs SDK Example
import tkinter as tk
from PIL import Image, ImageTk
import typing
import threading
import queue


class LiveViewCanvas(tk.Canvas):
    def __init__(self, parent, image_queue):
        # type: (typing.Any, queue.Queue) -> LiveViewCanvas
        self.image_queue = image_queue
        self._image_width = 0
        self._image_height = 0
        tk.Canvas.__init__(self, parent)
        self.pack()
        self._get_image()

    def _get_image(self):
        try:
            image = self.image_queue.get_nowait()
            self._image = ImageTk.PhotoImage(master=self, image=image)
            if (self._image.width() != self._image_width) or (
                self._image.height() != self._image_height
            ):
                # resize the canvas to match the new image size
                self._image_width = self._image.width()
                self._image_height = self._image.height()
                self.config(width=self._image_width, height=self._image_height)
            self.create_image(0, 0, image=self._image, anchor="nw")
        except queue.Empty:
            pass
        self.after(10, self._get_image)


""" ImageAcquisitionThread

This class derives from threading.Thread and is given a TLCamera instance during initialization. When started, the 
thread continuously acquires frames from the camera and converts them to PIL Image objects. These are placed in a 
queue.Queue object that can be retrieved using get_output_queue(). The thread doesn't do any arming or triggering, 
so users will still need to setup and control the camera from a different thread. Be sure to call stop() when it is 
time for the thread to stop.

"""


class ImageAcquisitionThread(threading.Thread):
    def __init__(self, camera):
        # type: (TLCamera) -> ImageAcquisitionThread
        super(ImageAcquisitionThread, self).__init__()
        self._camera = camera
        self._previous_timestamp = 0

        # setup color processing if necessary
        if self._camera.camera.camera_sensor_type != SENSOR_TYPE.BAYER:
            # Sensor type is not compatible with the color processing library
            self._is_color = False
        else:
            self._mono_to_color_sdk = self._camera._Thorcam__host
            self._image_width = self._camera.camera.image_width_pixels
            self._image_height = self._camera.camera.image_height_pixels
            self._mono_to_color_processor = (
                self._camera._Thorcam__host.mono2color_sdk.create_mono_to_color_processor(
                    SENSOR_TYPE.BAYER,
                    self._camera.camera.color_filter_array_phase,
                    self._camera.camera.get_color_correction_matrix(),
                    self._camera.camera.get_default_white_balance_matrix(),
                    self._camera.camera.bit_depth,
                )
            )
            self._is_color = True

        self._bit_depth = self._camera.camera.bit_depth
        self._camera.camera.image_poll_timeout_ms = (
            0  # Do not want to block for long periods of time
        )
        self._image_queue = queue.Queue(maxsize=2)
        self._stop_event = threading.Event()

    def get_output_queue(self):
        # type: (type(None)) -> queue.Queue
        return self._image_queue

    def stop(self):
        self._stop_event.set()

    def _get_color_image(self, frame):
        # type: (Frame) -> Image
        # verify the image size
        width = frame.image_buffer.shape[1]
        height = frame.image_buffer.shape[0]
        if (width != self._image_width) or (height != self._image_height):
            self._image_width = width
            self._image_height = height
            print(
                "Image dimension change detected, image acquisition thread was updated"
            )
        # color the image. transform_to_24 will scale to 8 bits per channel
        color_image_data = self._mono_to_color_processor.transform_to_24(
            frame.image_buffer, self._image_width, self._image_height
        )
        color_image_data = color_image_data.reshape(
            self._image_height, self._image_width, 3
        )
        # return PIL Image object
        return Image.fromarray(color_image_data, mode="RGB")

    def _get_image(self, frame):
        # type: (Frame) -> Image
        # no coloring, just scale down image to 8 bpp and place into PIL Image object
        scaled_image = frame.image_buffer >> (self._bit_depth - 8)
        return Image.fromarray(scaled_image)

    def run(self):
        while not self._stop_event.is_set():
            try:
                frame = self._camera.camera.get_pending_frame_or_null()
                if frame is not None:
                    if self._is_color:
                        pil_image = self._get_color_image(frame)
                    else:
                        pil_image = self._get_image(frame)
                    self._image_queue.put_nowait(pil_image)
            except queue.Full:
                # No point in keeping this image around when the queue is full, let's skip to the next one
                pass
            except Exception as error:
                print(
                    "Encountered error: {error}, image acquisition will stop.".format(
                        error=error
                    )
                )
                break
        print("Image acquisition has stopped")
        if self._is_color:
            self._mono_to_color_processor.dispose()
            # self._mono_to_color_sdk.dispose()
