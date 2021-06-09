import serial
import time
import re
import numpy as np
import yaml
import os
import threading
from abc import ABC, abstractmethod
from tifffile import imsave
import csv

from functools import partial
from .helpers import get_port
from .thorcam import ThorcamHost
from .spectrometer import Spectrometer
from .switchbox import Switchbox

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["characterizationline"]

## Line Methods
class CharacterizationLine:
    """High-level control object for characterization of samples in PASCAL"""

    def __init__(self, rootdir):
        self.axis = CharacterizationAxis()
        self.x0 = constants["x0"]  # position where gantry picks/places samples
        self.rootdir = rootdir

        self.switchbox = Switchbox()
        self.camerahost = ThorcamHost()
        self.darkfieldcamera = self.camerahost.spawn_camera(
            camid=constants["darkfield"]["cameraid"]
        )
        self.brightfieldcamera = self.camerahost.spawn_camera(
            camid=constants["brightfield"]["cameraid"]
        )
        self.spectrometer = Spectrometer()

        # all characterization stations (in order of measurement!)
        self.stations = [
            DarkfieldImaging(
                position=constants["darkfield"]["position"],
                rootdir=self.rootdir,
                camera=self.darkfieldcamera,
                lightswitch=self.switchbox.Switch(
                    constants["darkfield"]["switchindex"]
                ),
            ),
            PLImaging(
                position=constants["pl_imaging"]["position"],
                rootdir=self.rootdir,
                camera=self.darkfieldcamera,
                lightswitch=self.switchbox.Switch(
                    constants["pl_imaging"]["switchindex"]
                ),
            ),
            BrightfieldImaging(
                position=constants["brightfield"]["position"],
                rootdir=self.rootdir,
                camera=self.brightfieldcamera,
                lightswitch=self.switchbox.Switch(
                    constants["brightfield"]["switchindex"]
                ),
            ),
            TransmissionSpectroscopy(
                position=constants["transmission"]["position"],
                rootdir=self.rootdir,
                spectrometer=self.spectrometer,
                shutter=self.switchbox.Switch(constants["transmission"]["switchindex"]),
            ),
            PLSpectroscopy(
                position=constants["pl"]["position"],
                rootdir=self.rootdir,
                spectrometer=self.spectrometer,
                shutter=self.switchbox.Switch(constants["pl"]["switchindex"]),
            ),
        ]

    def run(self):
        """Pass a sample down the line and measure at each station"""
        for s in self.stations:
            self.axis.moveto(s.position)
            s.run()  # combines measure + save methods
        self.axis.moveto(self.x0)


class CharacterizationAxis:
    """Controls for the characterization line stage (1D axis)"""

    def __init__(
        self,
        port=None,
        serial_number=constants["axis"]["serialid"],
    ):
        # communication variables
        if port is None:
            self.port = get_port(serial_number)
        else:
            self.port = port
        self.POLLINGDELAY = constants["axis"][
            "pollingrate"
        ]  # delay between sending a command and reading a response, in seconds
        self.inmotion = False

        # characterizationline variables
        self.XLIM = (
            constants["axis"]["x_min"],
            constants["axis"]["x_max"],
        )
        self.position = None  # start at None's to indicate stage has not been homed.
        self.__targetposition = None
        self.TIMEOUT = constants["axis"][
            "timeout"
        ]  # max time allotted to characterizationline motion before flagging an error, in seconds
        self.POSITIONTOLERANCE = constants["axis"][
            "positiontolerance"
        ]  # tolerance for position, in mm
        self.MAXSPEED = constants["axis"]["speed_max"]  # mm/min
        self.MINSPEED = constants["axis"]["speed_min"]  # mm/min
        self.speed = self.MAXSPEED  # mm/min, default speed

        # connect to characterizationline by default
        self.connect()
        self.set_defaults()

    # communication methods
    def connect(self):
        self._handle = serial.Serial(port=self.port, timeout=1, baudrate=115200)
        self.update()
        # self.update_gripper()
        if self.position == max(
            self.XLIM
        ):  # this is what it shows when initially turned on, but not homed
            self.position = None
        self.__start_gripper_timeout_watchdog()
        # self.write('M92 X40.0 Y26.77 Z400.0')

    def disconnect(self):
        self._handle.close()
        del self._handle

    def set_defaults(self):
        self.write("G90")  # absolute coordinate system
        # self.write('M92 X26.667 Y26.667 Z200.0') #set steps/mm, randomly resets to defaults sometimes idk why
        self.write(
            "M92 X53.333"  # TODO Set default values here
        )  # set steps/mm, randomly resets to defaults sometimes idk why
        self.write(
            f"M203 X{self.MAXSPEED}"
        )  # set max speeds, steps/mm. Z is hardcoded, limited by lead screw hardware.
        self.set_speed_percentage(80)  # set speed to 80% of max

    def write(self, msg):
        self._handle.write(f"{msg}\n".encode())
        time.sleep(self.POLLINGDELAY)
        output = []
        while self._handle.in_waiting:
            line = self._handle.readline().decode("utf-8").strip()
            if line != "ok":
                output.append(line)
            time.sleep(self.POLLINGDELAY)
        return output

    def _enable_steppers(self):
        self.write("M18")

    def _disable_steppers(self):
        self.write("M17")

    def set_speed_percentage(self, p):
        if p < 0 or p > 100:
            raise Exception("Speed must be set by a percentage value between 0-100!")
        self.speed = (p / 100) * (self.MAXSPEED - self.MINSPEED) + self.MINSPEED
        self.write(f"G0 F{self.speed}")

    # movement methods

    def gohome(self):
        self.write("G28 X Y Z")
        self.update()

    def premove(self, x):
        """
        checks to confirm that all target positions are valid
        """
        if self.position == None:
            raise Exception(
                "Stage has not been homed! Home with self.gohome() before moving please."
            )

        if x > self.XLIM[1] or x < self.XLIM[0]:
            raise Exception(f"Invalid move - {x:.2f} is out of bounds")

        self.__targetposition = x
        return True

    def moveto(self, x: float):
        """internal command to execute a direct move from current location to new location"""
        if self.premove(x):
            self.write(f"G0 X{x} Y{y} Z{z}")
            return self._waitformovement()

    def moverel(self, x=0):
        """
        moves by coordinates relative to the current position
        """
        x += self.position
        self.moveto(x)

    def _waitformovement(self):
        """
        confirm that characterizationline has reached target position. returns False if
        target position is not reached in time allotted by self.characterizationlineTIMEOUT
        """
        self.inmotion = True
        start_time = time.time()
        time_elapsed = time.time() - start_time
        self._handle.write(f"M400\n".encode())
        self._handle.write(f"M118 E1 FinishedMoving\n".encode())
        reached_destination = False
        while not reached_destination and time_elapsed < self.TIMEOUT:
            time.sleep(self.POLLINGDELAY)
            while self._handle.in_waiting:
                line = self._handle.readline().decode("utf-8").strip()
                if line == "echo:FinishedMoving":
                    self.update()
                    if (
                        np.linalg.norm(
                            [
                                a - b
                                for a, b in zip(self.position, self.__targetposition)
                            ]
                        )
                        < self.POSITIONTOLERANCE
                    ):
                        reached_destination = True
                time.sleep(self.POLLINGDELAY)
            time_elapsed = time.time() - start_time

        self.inmotion = ~reached_destination
        return reached_destination


### Station Methods


class StationTemplate(ABC):
    """
    Template method that contains a skeleton of
    some algorithm, composed of calls to (usually) abstract primitive
    operations.

    Concrete subclasses should implement these operations, but leave the
    template method itself intact.
    """

    def __init__(self, position, savedir):
        self.position = position
        self.savedir = savedir
        if ~os.path.exists(savedir):
            os.mkdir(savedir)

    @abstractmethod
    def capture(self) -> None:
        """acquire data from station"""
        pass

    @abstractmethod
    def save(self) -> None:
        """save measurement data"""
        pass

    def run(self, *args, **kwargs) -> None:
        """acquire + save a measurement"""
        output = self.capture(*args, **kwargs)
        self.save(output)


class DarkfieldImaging(StationTemplate):
    def __init__(self, position, rootdir, camera, lightswitch):
        savedir = os.path.join(rootdir, "Darkfield")

        super().__init__(position=position, savedir=savedir)
        self.camera = camera
        self.lightswitch = lightswitch

    def capture(self):
        self.lightswitch.on()
        img = self.camera.capture()
        self.lightswitch.off()
        return img

    def save(self, img, sample):
        fname = f"{sample}_darkfield.tif"
        imsave(os.path.join(self.savedir, fname), img)


class PLImaging(StationTemplate):
    def __init__(self, position, rootdir, camera, lightswitch):
        savedir = os.path.join(rootdir, "PLImaging")

        super().__init__(position=position, savedir=savedir)
        self.camera = camera
        self.lightswitch = lightswitch

    def capture(self):
        self.lightswitch.on()
        img = self.camera.capture()
        self.lightswitch.off()
        return img

    def save(self, img, sample):
        fname = f"{sample}_darkfield.tif"
        imsave(os.path.join(self.savedir, fname), img)


class BrightfieldImaging(StationTemplate):
    def __init__(self, position, rootdir, camera, lightswitch):
        savedir = os.path.join(rootdir, "Brightfield")

        super().__init__(position=position, savedir=savedir)
        self.camera = camera
        self.lightswitch = lightswitch

    def capture(self):
        self.lightswitch.on()
        img = self.camera.capture()
        self.lightswitch.off()
        return img

    def save(self, img, sample):
        fname = f"{sample}_darkfield.tif"
        imsave(os.path.join(self.savedir, fname), img)


class TransmissionSpectroscopy(StationTemplate):
    def __init__(self, position, rootdir, spectrometer, shutter):
        savedir = os.path.join(rootdir, "Transmission")

        super().__init__(position=position, savedir=savedir)
        self.spectrometer = spectrometer
        self.shutter = shutter

    def capture(self):
        self.shutter.on()  # opens the shutter
        spectrum = self.spectrometer.capture()  # TODO - make this the HDR capture
        self.shutter.off()  # closes the shutter
        return spectrum

    def save(self, spectrum, sample):
        fname = f"{sample}_transmission.csv"
        with open(os.path.join(self.savedir, fname), "w") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(["Wavelength (nm)", "Transmittance"])
            for wl, t in spectrum:
                writer.writerow([wl, t])


class PLSpectroscopy(StationTemplate):
    def __init__(self, position, rootdir, spectrometer, lightswitch):
        savedir = os.path.join(rootdir, "PL")

        super().__init__(position=position, savedir=savedir)
        self.spectrometer = spectrometer
        self.lightswitch = lightswitch

    def capture(self):
        self.lightswitch.on()
        spectrum = self.spectrometer.capture()
        self.lightswitch.off()
        return spectrum

    def save(self, spectrum, sample):
        fname = f"{sample}_pl.csv"
        with open(os.path.join(self.savedir, fname), "w") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(["Wavelength (nm)", "PL (counts/second)"])
            for wl, t in spectrum:
                writer.writerow([wl, t])
