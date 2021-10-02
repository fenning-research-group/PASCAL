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

    def __init__(self, rootdir, gantry, switchbox: Switchbox):
        self.axis = CharacterizationAxis(gantry=gantry)
        self.rootdir = rootdir
        if not os.path.exists(self.rootdir):
            os.mkdir(self.rootdir)
        self.switchbox = switchbox
        self.shutter = Shutter()
        self.filterslider = FilterSlider()
        self.camerahost = ThorcamHost()
        self.darkfieldcamera = self.camerahost.spawn_camera(
            camid=constants["darkfield"]["cameraid"]
        )
        self.brightfieldcamera = self.camerahost.spawn_camera(
            camid=constants["brightfield"]["cameraid"]
        )
        # self.spectrometer = Spectrometer()
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
                slider=self.filterslider,
                shutter=self.shutter,
            ),
            PLSpectroscopy(
                position=constants["pl_red"]["position"],
                rootdir=self.rootdir,
                subdir="PL_635",
                spectrometer=self.spectrometer,
                slider=self.filterslider,
                shutter=self.shutter,
                lightswitch=self.switchbox.Switch(constants["pl_red"]["switchindex"]),
            ),
            PLPhotostability(
                position=constants["pl_blue"]["position"],
                rootdir=self.rootdir,
                subdir="PLPhotostability_405",
                spectrometer=self.spectrometer,
                slider=self.filterslider,
                shutter=self.shutter,
                lightswitch=self.switchbox.Switch(constants["pl_blue"]["switchindex"]),
            ),
        ]

        # state variables
        self._calibrated = False

    def run(self, samplename):
        """Pass a sample down the line and measure at each station"""
        for s in self.stations:
            self.axis.moveto(s.position)
            s.run(sample=samplename)  # combines measure + save methods
        self.axis.moveto(self.axis.TRANSFERPOSITION)

    def calibrate(self):
        """calibrate any stations that require it"""
        for s in self.stations:
            if hasattr(s, "calibrate"):
                print(f"Calibrating {s}")
                self.axis.moveto(s.position)
                s.calibrate()
        self.axis.moveto(self.axis.TRANSFERPOSITION)

        self._calibrated = True

    def set_directory(self, filepath):
        self.rootdir = filepath
        for s in self.stations:
            s.set_directory(filepath)


class CharacterizationAxis:
    """Controls for the characterization line stage (1D axis)"""

    def __init__(
        self,
        gantry,
        port=None,
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
        self._handle = serial.Serial(port=self.port, timeout=1, baudrate=115200)
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
        self.moveto(self.TRANSFERPOSITION)
        self.gantry.moveto(*self.p0)
        self.gantry.gui()
        self.coordinates = np.array(self.gantry.position)
        # self.gantry.moverel(z=10, zhop=False)
        self.__calibrated = True
        with open(
            os.path.join(CALIBRATION_DIR, f"characterizationaxis_calibration.yaml"), "w"
        ) as f:
            yaml.dump(self.coordinates, f)

    def _load_calibration(self):
        with open(
            os.path.join(CALIBRATION_DIR, f"characterizationaxis_calibration.yaml"), "r"
        ) as f:
            self.coordinates = np.array(yaml.load(f, Loader=yaml.FullLoader))
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
                    if self.position - self.__targetposition < self.POSITIONTOLERANCE:
                        reached_destination = True
                time.sleep(self.POLLINGDELAY)
            time_elapsed = time.time() - start_time

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
        self.position = x

    def movetotransfer(self):
        self.moveto(self.TRANSFERPOSITION)


### Station Methods


class StationTemplate(ABC):
    """
    Template method that contains a skeleton of
    some algorithm, composed of calls to (usually) abstract primitive
    operations.

    Concrete subclasses should implement these operations, but leave the
    template method itself intact.
    """

    def __init__(self, position, rootdir, subdir):
        self.position = position
        self._rootdir = rootdir
        self._subdir = subdir
        # self.set_directory(rootdir, subdir)

    def set_directory(self, rootdir, subdir=None):
        if subdir is None:
            subdir = self._subdir
        self.savedir = os.path.join(rootdir, subdir)
        if not os.path.exists(self.savedir):
            os.mkdir(self.savedir)

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


class DarkfieldImaging(StationTemplate):
    def __init__(self, position, rootdir, camera, lightswitch, subdir="Darkfield"):
        super().__init__(position=position, rootdir=rootdir, subdir=subdir)
        self.camera = camera
        self.lightswitch = lightswitch

    def capture(self):
        self.camera.exposure = 5e4  # 50 ms dwell time, in microseconds
        self.camera.frames = 20  # average 20 frames
        self.lightswitch.on()
        img = self.camera.capture()
        self.lightswitch.off()
        self.camera.frames = 1
        return img

    def save(self, img, sample):
        fname = f"{sample}_darkfield.tif"
        imwrite(os.path.join(self.savedir, fname), img, compression="zlib")


class PLImaging(StationTemplate):
    def __init__(
        self, position, rootdir, camera: Thorcam, lightswitch, subdir="PLImaging"
    ):
        super().__init__(position=position, rootdir=rootdir, subdir=subdir)
        self.camera = camera
        self.lightswitch = lightswitch
        self.hdr_times = [5e4, 2e5, 1e6, 5e6]  # 50 ms, 200 ms, 1 s dwell times

    def capture(self):
        """
        Take a series of PL images at exposure times specified in self.hdr_times

        Returns:
            imgs: dictionary of {dwelltime (ms): image}
        """
        self.camera.frames = 5  # average 5 frames
        imgs = {}

        self.lightswitch.on()
        time.sleep(1)  # LED lamp takes a second to turn on
        for t in self.hdr_times:
            self.camera.exposure_time = t
            imgs[int(t / 1000)] = self.camera.capture()  # save as ms exposure
        self.lightswitch.off()

        self.camera.frames = 1
        return imgs

    def save(self, imgs, sample):
        for t, img in imgs.items():
            fname = f"{sample}_plimage_{t}ms.tif"
            imwrite(os.path.join(self.savedir, fname), img, compression="zlib")


class BrightfieldImaging(StationTemplate):
    def __init__(self, position, rootdir, camera, lightswitch, subdir="Brightfield"):
        super().__init__(position=position, rootdir=rootdir, subdir=subdir)

        self.camera = camera
        self.lightswitch = lightswitch

    def capture(self):
        self.lightswitch.on()
        img = self.camera.capture()
        self.lightswitch.off()
        return img

    def save(self, img, sample):
        fname = f"{sample}_brightfield.tif"
        imwrite(os.path.join(self.savedir, fname), img, compression="zlib")


class TransmissionSpectroscopy(StationTemplate):
    def __init__(
        self,
        position,
        rootdir,
        spectrometer: Spectrometer,
        shutter: Shutter,
        slider: FilterSlider,
        subdir="Transmission",
    ):
        super().__init__(position=position, rootdir=rootdir, subdir=subdir)

        self.spectrometer = spectrometer
        self.shutter = shutter
        self.slider = slider
        self.hdr_times = [50, 200, 1000, 5000, 10000]  # ms
        self.NUMSCANS = 3  # take 2 scans per to reduce noise
        self.spectrometer._hdr_times = list(
            set(self.spectrometer._hdr_times + self.hdr_times)
        )

    def capture(self):
        # set scan parameters
        self.spectrometer.numscans = self.NUMSCANS
        hdrtimes0 = self.spectrometer._hdr_times
        self.spectrometer._hdr_times = self.hdr_times

        # open shutter + move filter slider
        threads = [
            Thread(
                target=self.slider.top_left
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
        self.spectrometer.numscans = 1
        self.spectrometer._hdr_times = hdrtimes0

        return wl, t

    def save(self, spectrum, sample):
        wl, t = spectrum
        fname = f"{sample}_transmission.csv"
        with open(os.path.join(self.savedir, fname), "w", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(["Wavelength (nm)", "Transmission (0-1)"])
            for wl_, t_ in zip(wl, t):
                writer.writerow([wl_, t_])

    def calibrate(self):
        self.slider.top_left()  # moves longpass filter out of the transmitted path
        self.shutter.close()  # close the shutter
        self.spectrometer.take_dark_baseline()
        print("spectrometer dark baselines taken")
        self.shutter.open()  # open the shutter
        self.spectrometer.take_light_baseline()
        print("spectrometer light baselines taken")
        self.shutter.close()  # closes the shutter


class PLSpectroscopy(StationTemplate):
    def __init__(
        self,
        position,
        rootdir,
        spectrometer: Spectrometer,
        lightswitch: SingleSwitch,
        slider: FilterSlider,
        shutter: Shutter,
        subdir="PL",
    ):
        super().__init__(position=position, rootdir=rootdir, subdir=subdir)
        self.spectrometer = spectrometer
        self.lightswitch = lightswitch
        self.shutter = shutter
        self.slider = slider
        self.hdr_times = [50, 200, 1000, 5000]
        self.spectrometer._hdr_times = list(
            set(self.spectrometer._hdr_times + self.hdr_times)
        )

    def capture(self):
        """
        captures high-depth resolution (HDR) PL spectrum with a few increasing dwell times.
        data at each wavelength uses the longest dwell time that didnt blow out the detector
        """
        threads = [
            Thread(
                target=self.slider.top_right
            ),  # move longpass filter into the detector path
            Thread(target=self.shutter.close),  # close the shutter to transmission lamp
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.lightswitch.on()  # turn on the laser
        all_cts = {}
        for t in self.hdr_times:
            self.spectrometer.dwelltime = t
            wl, cts = self.spectrometer.capture()
            all_cts[t] = cts
        self.lightswitch.off()  # turn off the laser

        return [wl, all_cts]

    def save(self, spectrum, sample):
        wl, all_cts = spectrum
        dwells = list(all_cts.keys())
        dwells.sort()
        cts = np.array([all_cts[d] for d in dwells]).T

        fname = f"{sample}_pl.csv"
        with open(os.path.join(self.savedir, fname), "w", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(["Dwelltimes (ms)"] + dwells)
            writer.writerow(["Wavelength (nm)"] + ["PL (counts)"] * len(dwells))
            for wl_, cts_ in zip(wl, cts):
                writer.writerow([wl_] + list(cts_))

    def calibrate(self):
        self.slider.top_right()  # moves longpass filter out of the transmitted path
        self.shutter.close()  # close the shutter
        self.spectrometer.take_dark_baseline(skip_repeats=True)
        print("PL dark baselines taken")


class PLPhotostability(StationTemplate):
    def __init__(
        self,
        position,
        rootdir,
        spectrometer: Spectrometer,
        lightswitch: SingleSwitch,
        slider: FilterSlider,
        shutter: Shutter,
        subdir="PLPhotostability",
    ):
        super().__init__(position=position, rootdir=rootdir, subdir=subdir)
        self.spectrometer = spectrometer
        self.lightswitch = lightswitch
        self.shutter = shutter
        self.slider = slider
        self.dwelltime = 2000
        self.spectrometer._hdr_times = list(
            set(self.spectrometer._hdr_times + [self.dwelltime])
        )

    def capture(self, duration=60):
        """Capture a continuous series of photoluminescence spectra

        Args:
            duration (int, optional): Total duration (seconds) for which to track spectra. Defaults to 60.

        Returns:
            [type]: [description]
        """
        threads = [
            Thread(
                target=self.slider.top_right
            ),  # move longpass filter into the detector path
            Thread(target=self.shutter.close),  # close the shutter to transmission lamp
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        times = []
        spectra = []
        self.spectrometer.dwelltime = self.dwelltime
        self.lightswitch.on()
        t0 = time.time()
        tnow = 0
        while tnow <= duration:
            wl, cts = self.spectrometer.capture()
            times.append(tnow)
            spectra.append(cts)
            tnow = time.time() - t0
        spectra = np.asarray(spectra)
        return wl, spectra, times

    def save(self, data, sample):
        wl, spectra, times = data
        fname = f"{sample}_photostability.csv"
        with open(os.path.join(self.savedir, fname), "w", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(["Dwelltime (ms)", self.spectrometer.dwelltime])
            writer.writerow(["Number of Spectra", len(spectra)])
            writer.writerow(["Data Start", "Times (s) of acquisition start ->"])
            writer.writerow(["Wavelength (nm)"] + [round(t_, 1) for t_ in times])
            for wl_, cts in zip(wl, spectra.T):
                writer.writerow([wl_] + cts.tolist())

    def calibrate(self):
        self.slider.top_right()  # moves longpass filter out of the transmitted path
        self.shutter.close()  # close the shutter
        self.spectrometer.take_dark_baseline(skip_repeats=True)
        print("PLPhotostability dark baselines taken")
