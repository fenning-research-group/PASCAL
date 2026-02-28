import serial
import socket
import websockets

import time
import re
import numpy as np
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton
import PyQt5
import yaml
import os
from functools import partial
from frgpascal.hardware.helpers import get_port

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader = yaml.FullLoader)

def setup_constants(communicator_instance):
    """
    Scrape the hardware constants for the given communicator_instance, add relevant attributes for motion control.
    """
    ci = communicator_instance
    attr_info = [
        # (name, constants key)
        ("POLLINGDELAY", "pollingrate"),
        ("_OVERALL_LIMS", "overall_gantry_limits"),
        ("_FRAMES", {"workspace": "workspace_limits", "opentrons": "opentrons_limits"}),
        ("TRANSITION_COORDINATES", "transition_coordinates"),
        ("CLEAR_COORDINATES", "clear_coordinates"),
        ("IDLE_COORDINATES", "idle_coordinates"),
        ("_currentframe", None),
        ("_ZLIM", None),
        ("position", [None, None, None]),
        ("_targetposition", [None, None, None]),
        ("GANTRYTIMEOUT", "timeout"),
        ("POSITIONTOLERANCE", "positiontolerance"),
        ("MAXSPEED", "speed_max"),
        ("MINSPEED", "speed_min"),
        ("ZHOP_HEIGHT", "zhop_height"),
        ("in_use", True)
    ]
    for ati in attr_info:
        name_, val_ = ati
        if isinstance(val_, dict):
            val = {k: ci._constants[v] for k, v in val_.items()}
        elif isinstance(val_, str):
            val = ci._constants[val_]
        else:
            val = val_
        setattr(
            obj = ci,
            name = name_,
            value = val
        )

class SerialCommunicator:
    """
    Communication via serial connections to execute the open-loop motion logic for the Gantry.

    Designed for a particular use with a BigTreeTech SKR Mini E3 V2.0 board,
    to handle one open-loop stepper motor per axis.

    Parameters
    ----------
    port : str, optional
        The COM_Port string of the USB-A port -> PCB connection. Defaults to None.
        If None, then the port is auto-assigned via lookup of pre-tabulated vid/pid saved within `frgpascal.hardware.hardwareconstants.yaml`.
    """
    def __init__(self, port):
        self._constants = constants["gantry_v2"]["serial_connection"]
        if port is None:
            self.port = get_port(self._constants["device_identifiers"])
        setup_constants(
            communicator_instance = self
        )
        self.speed = self.MAXSPEED
    
    def connect(self):
        self._handle = serial.Serial(port = self.port, timeout = 1, baudrate = 115200)
        self.update()
        if self.position == [
            self._OVERALL_LIMS["x_max"],
            self._OVERALL_LIMS["y_max"],
            self._OVERALL_LIMS["z_max"]
        ]:
            self.position = [None, None, None]
        self.set_defaults()
        print("Connected to gantry via serial")

    def set_defaults(self):
        """Load the default motor configurations.
        """
        self.write("M501")  # load defauls from EEPROM
        self.write("G90")   # absolute coordinate system
        # self.write("M92 X79.5")   # steps/mm is using 2mm pitch belt on x-axis
        self.write("M92 X53.333 Y53.333 Z200")  # steps/mm 3mm pitch belt on y, x axis, 2mm leadscrew on z-axis
        self.write("M906 X800 Y800 Z800 E1")    # set driver currents
        self.write("M84 S0")    # disable stepper timeouts
        self.write(
            f"M203 X{self.MAXSPEED} Y{self.MAXSPEED} Z20.00"
        )   # set max speeds, steps/mm. Z is hardcoded, limited by leadscrew hardware
        self.set_speed_percentage(80)
    
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

    def update(self):
        found_coordinates = False
        while not found_coordinates:
            output = self.write("M114") # get current position
            for line in output:
                if line.startswith("X:"):
                    x = float(re.findall(r"X:(\S*)", line)[0])
                    y = float(re.findall(r"Y:(\S*)", line)[0])
                    z = float(re.findall(r"Z:(\S*)", line)[0])
                    found_coordinates = True
                    break
        self.position = [x, y, z]
        self._currentframe = self._target_frame(*self.position)
        print(f"\t\t{self._currentframe}")
        self._ZLIM = self._FRAMES[self._currentframe]["z_max"]
    
    def set_speed_percentage(self, p):
        if (p < 0) or (p > 100):
            raise Exception("Speed must be set by a percentage value between 0-100!")
        self.speed = (p / 100) * (self.MAXSPEED - self.MINSPEED) + self.MINSPEED
        self.write(
            msg = f"G0 F{self.speed}"
        )

class SocketCommunicator:
    """
    Communication using sockets to execute partially closed-loop motion logic for the Gantry.

    Designed for a particular use with a Duet 3 Mini 5+ Ethernet plus 2XD Expansion Board,
    to handle dual X-axis closed-loop stepper motors with HSS57 external drivers, and 
    open-loop Y and Z axis stepper motors driven by on-board TMC2209 drivers.
    """
    def __init__(self):
        self._purpose = "Store relevant motion settings for the Gantry when using a Duet 3 Mini 5+ Ethernet control board for closed-loop dual X and open-loop Y, Z stepper motors"

class WebsocketCommunicator:
    """
    Communication using websockets to execute partially closed-loop motion logic for the Gantry.

    Designed for a particular use with a Duet 3 Mini 5+ Ethernet plus 2XD Expansion Board,
    to handle dual X-axis closed-loop stepper motors with HSS57 external drivers, and 
    open-loop Y and Z axis stepper motors driven by on-board TMC2209 drivers.
    """

class Gantry:
    """
    General class for interfacing with the 3-axis motion Gantry for coordination of sample transfers.

    Parameters
    ----------
    name : str
        name of workspaces, for logging purposes.
    pitch : tuple
        Space between neighboring slots (x,y) (mm). Assumes workspace is 2D, parallel to `frgpascal.hardware.gantry.Gantry` XY plane.
    gridsize : tuple
        Number of slots available (x,y)
    gantry : `frgpascal.hardware.gantry.Gantry`
        Gantry control object, needed for calibration.
    gripper : `frgpascal.hardware.gripper.Gripper`
        Gripper control object, needed for calibration.
    p0 : list, optional
        approximate location of the lower left slot of the labware, for calibration initial point.
    testslots : list, optional
        Slots with which to calibrate the plane tilt from. Defaults to None.
    z_clearance : float, optional
        Vertical clearance (mm) to give when calibrating points, to avoid crashes. Defaults to 5.
    openwidth : float, optional
        Width (mm) to open gripper to when picking samples from this workspace. Defaults to 20.
    """
    def __init__(
            self,
            communicator_choice = None,
            **communicate_kwargs
    ):
        self._communicator = self._setup_connection(
            connect_version = communicator_choice,
            **communicate_kwargs,
        )
    def _setup_connection(
            self,
            connect_version = "socket",
            **communicate_kwargs
    ):
        connectors = {
            "serial": SerialCommunicator,
            "socket": SocketCommunicator,
            "websocket": WebsocketCommunicator
        }
        try:
            connect_class = connectors[connect_version]
        except KeyError:
            raise ValueError(f"Unknown communication version! {connect_version} is not currently supported, I'd suggest trying `socket`")
        return connect_class(**communicate_kwargs)
    
    def update(self):
        self._communicator.update()
        self.__grippper_last_opened = time.time()

    def go_home(self):
        self._communicator.write("G28 X Y Z")
        self.update()
        self.movetoclear()