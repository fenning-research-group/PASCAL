import serial
import time
import re
import numpy as np
import yaml
import os
from threading import Thread
from abc import ABC, abstractmethod
from tifffile import imwrite
import csv
import json

try:
    from typing import Literal
except:
    from typing_extensions import Literal

from frgpascal.hardware.helpers import get_port
from frgpascal.hardware.thorcam import Thorcam, ThorcamHost
from frgpascal.hardware.spectrometer import Spectrometer
from frgpascal.hardware.switchbox import SingleSwitch, Switchbox
from frgpascal.hardware.shutter import Shutter
from frgpascal.hardware.filterslider import FilterSlider

MODULE_DIR = os.path.dirname(__file__)
CALIBRATION_DIR = os.path.join(MODULE_DIR, "calibrations")
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["characterizationline"]


## Line Methods
class CharacterizationLine:
    """High-level control object for characterization of samples in PASCAL"""

    def __init__(self, rootdir, gantry, switchbox: Switchbox, sample_size: str = Literal["square_10mm", "square_17mm", "square_25.3mm"]):
        self.axis = CharacterizationAxis(gantry=gantry, sample_size = sample_size)
        self.rootdir = rootdir
        #print(self.rootdir) ##added comment
        if not os.path.exists(self.rootdir):
            os.mkdir(self.rootdir)
            # print("made a new directory") ##added comment
        self.switchbox = switchbox
        print("switchbox connected") ##added comment
        self.shutter = Shutter()
        self.filterslider = FilterSlider()
        self.camerahost = ThorcamHost()
        self.darkfieldcamera = self.camerahost.spawn_camera(
            camid=constants["stations"]["darkfield"]["cameraid"]
        )
        self.brightfieldcamera = self.camerahost.spawn_camera(
            camid=constants["stations"]["brightfield"]["cameraid"]
        )
        self.spectrometer = Spectrometer()

        # all characterization stations (in order of measurement!)
        self.stations = {
            s.name: s
            for s in [
                PLPhotostability(
                    position=constants["stations"]["pl_blue"]["position"],
                    rootdir=self.rootdir,
                    spectrometer=self.spectrometer,
                    slider=self.filterslider,
                    shutter=self.shutter,
                    lightswitch=self.switchbox.Switch(
                        constants["stations"]["pl_blue"]["switchindex"]
                    ),
                ),
                PLSpectroscopy(
                    position=constants["stations"]["pl_red"]["position"],
                    rootdir=self.rootdir,
                    spectrometer=self.spectrometer,
                    slider=self.filterslider,
                    shutter=self.shutter,
                    lightswitch=self.switchbox.Switch(
                        constants["stations"]["pl_red"]["switchindex"]
                    ),
                ),
                TransmissionSpectroscopy(
                    position=constants["stations"]["transmission"]["position"],
                    rootdir=self.rootdir,
                    spectrometer=self.spectrometer,
                    slider=self.filterslider,
                    shutter=self.shutter,
                ),
                BrightfieldImaging(
                    position=constants["stations"]["brightfield"]["position"],
                    rootdir=self.rootdir,
                    camera=self.brightfieldcamera,
                    lightswitch=self.switchbox.Switch(
                        constants["stations"]["brightfield"]["switchindex"]
                    ),
                ),
                DarkfieldImaging(
                    position=constants["stations"]["darkfield"]["position"],
                    rootdir=self.rootdir,
                    camera=self.darkfieldcamera,
                    lightswitch=self.switchbox.Switch(
                        constants["stations"]["darkfield"]["switchindex"]
                    ),
                ),
                PLImaging(
                    position=constants["stations"]["pl_imaging"]["position"],
                    rootdir=self.rootdir,
                    camera=self.darkfieldcamera,
                    lightswitch=self.switchbox.Switch(
                        constants["stations"]["pl_imaging"]["switchindex"]
                    ),
                ),
            ]
        }

        # state variables
        self._calibrated = False

    def run(self, samplename, details):
        """Pass a sample down the line and measure at each station"""
        folder = self._create_measurement_folder(samplename)
        for task in details["characterization_tasks"]:
            station = self.stations[task["name"]]
            station.set_directory(folder)
            self.axis.moveto(station.position)
            station.run(
                sample=samplename, **task["details"]
            )  # combines measure + save methods
        self.axis.moveto(self.axis.TRANSFERPOSITION)

    def calibrate(self, netlist_fpath: str):
        """calibrate any stations that require it"""

        with open(netlist_fpath, "r") as f:
            instructions = json.load(f)["baselines_required"]

        for station_name, exposure_times in instructions.items():
            station = self.stations[station_name]
            if hasattr(station, "calibrate"):
                self.axis.moveto(station.position)
                station.calibrate(exposure_times=exposure_times)

        self.axis.moveto(self.axis.TRANSFERPOSITION)
        self._calibrated = True

    def set_directory(self, filepath):
        self.rootdir = filepath
        if not os.path.exists(self.rootdir):
            os.makedirs(self.rootdir)
        # for s in self.stations.values():
        #     s.set_directory(filepath)

    def _create_measurement_folder(self, samplename):
        if not os.path.exists(os.path.join(self.rootdir, samplename)):
            os.mkdir(os.path.join(self.rootdir, samplename))

        i = 0
        while os.path.exists(
            os.path.join(self.rootdir, samplename, f"characterization{i}")
        ):
            i += 1

        fid = os.path.join(self.rootdir, samplename, f"characterization{i}")
        os.mkdir(fid)
        return fid


class CharacterizationAxis:
    """Controls for the characterization line stage (1D axis)"""

    def __init__(
        self, gantry, port=None, sample_size: str = Literal["square_10mm", "square_17mm", "square_25.3mm"]
    ):
        # communication variables
        if port is None:
            self.port = get_port(constants["axis"]["device_identifiers"])
        else:
            self.port = port
        self.POLLINGDELAY = constants["axis"][
            "pollingrate"
        ]  # delay between sending a command and reading a response, in seconds
        self.inmotion = False

        # characterizationline variables
        self._SAMPLESIZEOPTION = sample_size
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
        self.gantry = gantry
        self.__calibrated = False  # calibrate gantry transfer coordinates
        self.TRANSFERPOSITION = constants["axis"]["transfer_position"]
        self.p0 = constants["axis"]["p0"]
        # connect to characterizationline by default
        self.connect()
        self.set_defaults()

    # communication methods
    def connect(self):
        print("Attempting to connect to cl.axis")
        self._handle = serial.Serial(port=self.port, timeout=1, baudrate=115200)
        if self._handle is None:
            print(self._handle)
            print("there is an issue with the port/serial connection")
        self.update()
        # self.update_gripper()
        if self.position == max(
            self.XLIM
        ):  # this is what it shows when initially turned on, but not homed
            self.position = None
        print("Connected to characterization axis")
        # self.write('M92 X40.0 Y26.77 Z400.0')

    def disconnect(self):
        self._handle.close()
        del self._handle

    def __call__(self):
        """Calling the characterization axis object will return its gantry coordinates. For consistency with the callable nature of gridded hardware (storage, hotplate, etc)

        Raises:
                        Exception: If spincoater position is not calibrated, error will thrown.

        Returns:
                        tuple: (x,y,z) coordinates for gantry to pick/place sample on spincoater chuck.
        """
        if self.__calibrated == False:
            raise Exception(
                f"Need to calibrate characterization axis position before use!"
            )
        self.movetotransfer()
        return self.coordinates

    # gantry transfer position calibration methods
    def calibrate(self):
        """Prompt user to manually position the gantry over the spincoater using the Gantry GUI. This position will be recorded and used for future pick/place operations to the spincoater chuck"""
        # self.gantry.moveto(z=self.gantry.OT2_ZLIM, zhop=False)
        # self.gantry.moveto(x=self.gantry.OT2_XLIM, y=self.gantry.OT2_YLIM, zhop=False)
        # self.gantry.moveto(x=self.p0[0], y=self.p0[1], avoid_ot2=False, zhop=False)
        if self.gantry.in_use:
            self.moveto(self.TRANSFERPOSITION)
            self.gantry.moveto(*self.p0)
            self.gantry.gui()
            self.coordinates = np.array(self.gantry.position)
            # self.gantry.moverel(z=10, zhop=False)
            self.__calibrated = True
            with open(os.path.join(CALIBRATION_DIR, "characterizationaxis_calibration.yaml"), "r") as f:
                old = yaml.safe_load(f)
            old[self._SAMPLESIZEOPTION] = self.coordinates
            with open(
                os.path.join(CALIBRATION_DIR, f"characterizationaxis_calibration.yaml"), "w"
            ) as f:
                # yaml.dump(self.coordinates.tolist(), f)
                yaml.dump(old)
        else:
            print("The Gantry is not being used in this PASCAL instance.")

    def _load_calibration(self):
        with open(
            os.path.join(CALIBRATION_DIR, f"characterizationaxis_calibration.yaml"), "r"
        ) as f:
            self.coordinates = np.array(yaml.load(f, Loader=yaml.FullLoader)[self._SAMPLESIZEOPTION])
        self.__calibrated = True

    def set_defaults(self):
        self.write("M501")  # load settings from EEPROM
        self.write("G90")  # absolute coordinate system
        # self.write(
        #     "M92 X320.00"  # TODO Set default values here
        # )  # set steps/mm, randomly resets to defaults sometimes idk why

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
        self.write("M17")

    def _disable_steppers(self):
        self.write("M18")

    # def set_speed_percentage(self, p):
    #     if p < 0 or p > 100:
    #         raise Exception("Speed must be set by a percentage value between 0-100!")
    #     self.speed = (p / 100) * (self.MAXSPEED - self.MINSPEED) + self.MINSPEED
    #     self.write(f"G0 F{self.speed}")

    # movement methods

    def gohome(self):
        self.write("G28 X")
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
        if self.__targetposition == self.position:
            # print('pascal evil')
            return False  # already at target position
        return True

    def moveto(self, x: float):
        """internal command to execute a direct move from current location to new location"""
        if self.premove(x):
            self.write(f"G0 X{x}")
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
        print(f"\ttarget position: {self.__targetposition}")
        print(f"\tcurrent position: {self.position}")
        self.inmotion = True
        start_time = time.time()
        time_elapsed = time.time() - start_time
        time_elapsed_2 = time.time() - start_time
        self._handle.write(f"M400\n".encode())
        self._handle.write(f"M118 E1 FinishedMoving\n".encode())
        reached_destination = False
        while not reached_destination and time_elapsed < self.TIMEOUT:
            time.sleep(self.POLLINGDELAY)
            print(f"{self._handle.in_waiting} nawwww")
            while not self._handle.in_waiting and time_elapsed_2 < self.TIMEOUT:
                time.sleep(2*self.POLLINGDELAY)
                print('waiting for serial.Serial to have nonzero bytes available to read')
                time_elapsed_2 = time.time() - start_time
            while self._handle.in_waiting:
                line = self._handle.readline().decode("utf-8").strip()
                if line == "echo:FinishedMoving":
                    print(f"\t\tEncoder thinks we have finished moving, time to update our self.position")
                    self.update()
                    print(f"\t\tOur updated position has been saved as {self.position}")
                    if self.position - self.__targetposition < self.POSITIONTOLERANCE:
                        print(f"\tSUCCESS!")
                        reached_destination = True
                    else:
                        print("pascal evil yet again")
                else:
                    print(f"\tOutput message from the self._handle:\n\t\t{line}")
                time.sleep(self.POLLINGDELAY)
            time_elapsed = time.time() - start_time

        if (time_elapsed >= self.TIMEOUT) or (time_elapsed_2 >= self.TIMEOUT):
            print("cl.axis._waitformovement timed-out, so the final position of the motor was not updated from the initial position.")
            print("time for the backup position definition while-loop")
            reached_destination = False
            while not reached_destination:
                time.sleep(self.POLLINGDELAY)
                position0 = self._getposition()
                time.sleep(self.POLLINGDELAY*5)
                position1 = self._getposition()
                if position0 == position1:
                    if position0 is not None:
                        self.position = position0
                        reached_destination = True
                        print(f"\tposition has been brute-forced to update to the current location of {self.position}")
                    elif position0 is None:
                        raise ValueError("cl.axis._getposition failed to return a valid position!")

        self.inmotion = False
        return reached_destination

    def update(self):
        found_coordinates = False
        while not found_coordinates:
            output = self.write("M114")  # get current position
            for line in output:
                if line.startswith("X:"):
                    x = float(re.findall(r"X:(\S*)", line)[0])
                    found_coordinates = True
                    break
        print(f"\tWithin self.update, the found_coordinates conditional has been defined to be {found_coordinates}")
        self.position = x

    def movetotransfer(self):
        self.moveto(self.TRANSFERPOSITION)

    def _getposition(self):
        x = None
        found_coordinates = False
        while not found_coordinates:
            output = self.write("M114") # get current position
            for line in output:
                if line.startswith("X:"):
                    x = float(re.findall(r"X:(\S*)", line)[0])
                    found_coordinates = True
                    break
        return x


### Station Methods


class CharacterizationStationTemplate(ABC):
    """
    Template method that contains a skeleton of
    some algorithm, composed of calls to (usually) abstract primitive
    operations.

    Concrete subclasses should implement these operations, but leave the
    template method itself intact.
    """

    def __init__(self, position: float, rootdir: str, name: str):
        self.position = position
        self._rootdir = rootdir
        self.name = name

    def set_directory(self, rootdir):
        self.savedir = rootdir
        # self.savedir = os.path.join(rootdir, self.name)
        # if not os.path.exists(self.savedir):
        #     os.mkdir(self.savedir)

    @abstractmethod
    def capture(self) -> None:
        """acquire data from station"""
        pass

    @abstractmethod
    def save(self) -> None:
        """save measurement data"""
        pass

    def run(self, sample, *args, **kwargs) -> None:
        """acquire + save a measurement"""
        output = self.capture(*args, **kwargs)
        self.save(output, sample=sample)


class DarkfieldImaging(CharacterizationStationTemplate):
    def __init__(
        self, position: float, rootdir: str, camera: Thorcam, lightswitch: SingleSwitch
    ):
        super().__init__(position=position, rootdir=rootdir, name="Darkfield")
        self.camera = camera
        self.lightswitch = lightswitch
        self.DEFAULT_EXPOSURE_TIME = 0.05  # dwelltime, seconds
        self.DEFAULT_NUM_FRAMES = 50  # average 500 frames

    def capture(self, **kwargs):

        self.camera.exposure_time = kwargs.get(
            "exposure_time", self.DEFAULT_EXPOSURE_TIME
        )
        self.camera.num_frames = kwargs.get("num_frames", self.DEFAULT_NUM_FRAMES)
        self.lightswitch.on()
        img = self.camera.capture()
        self.lightswitch.off()
        self.camera.num_frames = 1
        return img

    def save(self, img, sample):
        fname = f"{sample}_darkfield.tif"
        imwrite(
            os.path.join(self.savedir, fname),
            img,
            compression="zlib",
            resolution=(1.0 / 1.528, 1.0 / 1.528),  # 1 pixel = 1.528 um
            metadata={"unit": "um"},
        )


class PLImaging(CharacterizationStationTemplate):
    def __init__(
        self, position: float, rootdir: str, camera: Thorcam, lightswitch: SingleSwitch
    ):
        super().__init__(position=position, rootdir=rootdir, name="PLImaging")
        self.camera = camera
        self.lightswitch = lightswitch
        self.DEFAULT_EXPOSURE_TIMES = [
            0.05,
            0.2,
            1,
            3,
        ]  # 50 ms, 200 ms, 1 s dwell times
        self.DEFAULT_NUM_FRAMES = 5  # average 500 frames

    def capture(self, **kwargs):
        """
        Take a series of PL images at exposure times specified in self.hdr_times

        Returns:
            imgs: dictionary of {dwelltime (ms): image}
        """
        exposure_times = kwargs.get("exposure_times", self.DEFAULT_EXPOSURE_TIMES)
        self.camera.num_frames = kwargs.get("num_frames", self.DEFAULT_NUM_FRAMES)
        imgs = {}

        self.lightswitch.on()
        time.sleep(1)  # LED lamp takes a second to turn on
        for t in exposure_times:
            self.camera.exposure_time = t
            imgs[t] = self.camera.capture()  # save as ms exposure
        self.lightswitch.off()

        self.camera.num_frames = 1
        return imgs

    def save(self, imgs, sample):
        for t, img in imgs.items():
            fname = f"{sample}_plimage_{int(t*1e3)}ms.tif"
        imwrite(
            os.path.join(self.savedir, fname),
            img,
            compression="zlib",
            resolution=(1.0 / 1.528, 1.0 / 1.528),  # 1 pixel = 1.528 um
            metadata={"unit": "um"},
        )


class BrightfieldImaging(CharacterizationStationTemplate):
    def __init__(
        self, position: float, rootdir: str, camera: Thorcam, lightswitch: SingleSwitch
    ):
        super().__init__(position=position, rootdir=rootdir, name="Brightfield")

        self.camera = camera
        self.lightswitch = lightswitch
        self.DEFAULT_EXPOSURE_TIME = 0.05  # 50 ms dwell time
        self.DEFAULT_NUM_FRAMES = 1

    def capture(self, **kwargs):
        self.camera.exposure_time = kwargs.get(
            "exposure_time", self.DEFAULT_EXPOSURE_TIME
        )
        self.camera.num_frames = kwargs.get("num_frames", self.DEFAULT_NUM_FRAMES)
        self.lightswitch.on()
        img = self.camera.capture()
        self.lightswitch.off()
        return img

    def save(self, img, sample):
        fname = f"{sample}_brightfield.tif"
        imwrite(os.path.join(self.savedir, fname), img, compression="zlib")


class TransmissionSpectroscopy(CharacterizationStationTemplate):
    def __init__(
        self,
        position: float,
        rootdir: str,
        spectrometer: Spectrometer,
        shutter: Shutter,
        slider: FilterSlider,
    ):
        super().__init__(position=position, rootdir=rootdir, name="Transmission")

        self.spectrometer = spectrometer
        self.shutter = shutter
        self.slider = slider
        self.DEFAULT_EXPOSURE_TIMES = [0.015, 0.05, 0.2, 1, 5, 15]  # ms
        self.DEFAULT_NUM_SCANS = 3  # take 2 scans per to reduce noise

    def capture(self, **kwargs):
        # set scan parameters
        exposuretimes = kwargs.get("exposure_times", self.DEFAULT_EXPOSURE_TIMES)
        exposuretimes.sort()
        numscans = kwargs.get("numscans", self.DEFAULT_NUM_SCANS)
        self.spectrometer.num_scans = numscans

        exposuretimes_0 = self.spectrometer._exposure_times
        self.spectrometer._exposure_times = exposuretimes

        # open shutter + move filter slider
        threads = [
            Thread(
                # target=self.slider.top_left
                target = self.slider.bottom_right
            ),  # move longpass filter out of the detector path
            Thread(target=self.shutter.open),  # open the shutter to transmission lamp
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wl, t = self.spectrometer.transmission_hdr()

        # close shutter, return to defaults
        self.shutter.close()
        self.spectrometer.num_scans = 1
        self.spectrometer._exposure_times = exposuretimes_0
        self.spectrometer.exposure_time = 0.02  # set to short dwelltime (seconds) to prevent bleeding into next measurement

        return wl, t

    def save(self, spectrum, sample):
        wl, t = spectrum
        fname = f"{sample}_transmission.csv"
        with open(os.path.join(self.savedir, fname), "w", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(["Wavelength (nm)", "Transmission (0-1)"])
            for wl_, t_ in zip(wl, t):
                writer.writerow([wl_, t_])

    def calibrate(self, exposure_times: list):
        # self.slider.top_left()  # moves longpass filter out of the transmitted path
        self.slider.bottom_right()
        self.shutter.close()  # close the shutter
        self.spectrometer._exposure_times = exposure_times
        self.spectrometer.take_dark_baseline(skip_repeats=True)
        print("Transmission dark baselines taken")
        self.shutter.open()  # open the shutter
        self.spectrometer.take_light_baseline(skip_repeats=True)
        print("Transmission light baselines taken")
        self.shutter.close()  # closes the shutter


class PLSpectroscopy(CharacterizationStationTemplate):
    def __init__(
        self,
        position: float,
        rootdir: str,
        spectrometer: Spectrometer,
        lightswitch: SingleSwitch,
        slider: FilterSlider,
        shutter: Shutter,
    ):
        super().__init__(position=position, rootdir=rootdir, name="PL_635nm")
        self.spectrometer = spectrometer
        self.lightswitch = lightswitch
        self.shutter = shutter
        self.slider = slider
        self.DEFAULT_EXPOSURE_TIMES = [1, 5, 20]
        self.DEFAULT_NUM_SCANS = 1  # take 2 scans per to reduce noise

    def capture(self, **kwargs):
        """
        captures high-depth resolution (HDR) PL spectrum with a few increasing dwell times.
        data at each wavelength uses the longest dwell time that didnt blow out the detector
        """
        threads = [
            Thread(
                # target=self.slider.top_right
                target=self.slider.bottom_left
            ),  # move longpass filter into the detector path
            Thread(target=self.shutter.close),  # close the shutter to transmission lamp
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        exposuretimes = kwargs.get("exposure_times", self.DEFAULT_EXPOSURE_TIMES)
        numscans = kwargs.get("num_scans", self.DEFAULT_NUM_SCANS)
        self.spectrometer.num_scans = numscans
        self.lightswitch.on()  # turn on the laser
        all_cts = {}
        for t in exposuretimes:
            self.spectrometer.exposure_time = t
            wl, cts = self.spectrometer.capture()
            all_cts[t] = cts
        self.lightswitch.off()  # turn off the laser
        self.spectrometer.num_scans = 1
        self.spectrometer.exposure_time = (
            0.02  # fast dwelltime to prevent bleeding over into next measurement
        )
        return [wl, all_cts]

    def save(self, spectrum, sample):
        wl, all_cts = spectrum
        dwells = list(all_cts.keys())
        dwells.sort()
        cts = np.array([all_cts[d] for d in dwells]).T

        fname = f"{sample}_pl.csv"
        with open(os.path.join(self.savedir, fname), "w", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(["Dwelltimes (s)"] + dwells)
            writer.writerow(["Wavelength (nm)"] + ["PL (counts)"] * len(dwells))
            for wl_, cts_ in zip(wl, cts):
                writer.writerow([wl_] + list(cts_))

    def calibrate(self, exposure_times: list):
        print(f"Taking dark baselines for {self}")
        self.spectrometer._exposure_times = exposure_times
        threads = [
            Thread(
                # target=self.slider.top_right
                target=self.slider.bottom_left
            ),  # move longpass filter into the detector path
            Thread(target=self.shutter.close),  # close the shutter to transmission lamp
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.spectrometer.take_dark_baseline(skip_repeats=True)
        print("PL dark baselines taken")


class PLPhotostability(CharacterizationStationTemplate):
    def __init__(
        self,
        position: float,
        rootdir: str,
        spectrometer: Spectrometer,
        lightswitch: SingleSwitch,
        slider: FilterSlider,
        shutter: Shutter,
    ):
        super().__init__(
            position=position, rootdir=rootdir, name="Photostability_405nm"
        )
        self.spectrometer = spectrometer
        self.lightswitch = lightswitch
        self.shutter = shutter
        self.slider = slider
        self.DEFAULT_EXPOSURE_TIME = 2000  # ms
        self.DEFAULT_DURATION = 120  # seconds

    def capture(self, **kwargs):
        """Capture a continuous series of photoluminescence spectra

        Args:
            duration (int, optional): Total duration (seconds) for which to track spectra. Defaults to 60.

        Returns:
            [type]: [description]
        """
        threads = [
            Thread(
                # target=self.slider.top_right
                target=self.slider.bottom_left
            ),  # move longpass filter into the detector path
            Thread(target=self.shutter.close),  # close the shutter to transmission lamp
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        times = []
        spectra = []
        duration = kwargs.get("duration", self.DEFAULT_DURATION)
        self.spectrometer.exposure_time = kwargs.get(
            "exposure_time", self.DEFAULT_EXPOSURE_TIME
        )
        self.spectrometer.num_scans = 1
        self.lightswitch.on()
        t0 = time.time()
        tnow = 0
        while tnow <= duration:
            wl, cts = self.spectrometer.capture()
            times.append(tnow)
            spectra.append(cts)
            tnow = time.time() - t0
        spectra = np.asarray(spectra)
        self.lightswitch.off()
        return wl, spectra, times

    def save(self, data, sample):
        wl, spectra, times = data
        fname = f"{sample}_photostability.csv"
        with open(os.path.join(self.savedir, fname), "w", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(["Dwelltime (s)", self.spectrometer.exposure_time])
            writer.writerow(["Number of Spectra", len(spectra)])
            writer.writerow(["Data Start", "Times (s) of acquisition start ->"])
            writer.writerow(["Wavelength (nm)"] + [round(t_, 1) for t_ in times])
            for wl_, cts in zip(wl, spectra.T):
                writer.writerow([wl_] + cts.tolist())

    def calibrate(self, exposure_times: list):
        threads = [
            Thread(
                # target=self.slider.top_right
                target=self.slider.bottom_left
            ),  # move longpass filter into the detector path
            Thread(target=self.shutter.close),  # close the shutter to transmission lamp
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.spectrometer._exposure_times = exposure_times
        self.spectrometer.take_dark_baseline(skip_repeats=True)
        print("PLPhotostability dark baselines taken")
