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
try:
    from typing import Union, List, Literal, Optional
except:
    from typing import Union, List, Optional
    from typing_extensions import Literal
MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader = yaml.FullLoader)

def setup_constants(communicator_instance):
    """
    Scrape the hardware constants for the given communicator_instance.

    Add common attributes for motion control which will be used regardless of 
    the type of communicator_instance. Checks the type of communicator_instance, 
    and adds special cases as attributes.
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
        ("TRANSITION_NUDGE", "transition_nudge"),
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
    #TODO: handle special cases
    # spec_attrs = []
    # if isinstance(communicator_instance, SerialCommunicator):
    #     # add special constants for the SerialCommunicator, if they have not yet been defined as attributes
    # elif isinstance(communicator_instance, SocketCommunicator):
    #     # add special constants for just the SocketCommunicator
    # elif isinstance(communicator_instance, WebsocketCommunicator):

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
        self.set_speed_percentage(p = 80)
    
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
        """
        Enables the motors on the gantry
        """
        self.write("M17")
    
    def _disable_steppers(self):
        """
        Disables the motors on the gantry
        """
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
        """
        Multiplies the self.speed attribute by a percentage p

        Parameters
        ----------
        p : float
            the percentage by which the speed should be multiplied by
        """
        if (p < 0) or (p > 100):
            raise Exception("Speed must be set by a percentage value between 0-100!")
        self.speed = (p / 100) * (self.MAXSPEED - self.MINSPEED) + self.MINSPEED
        self.write(
            msg = f"G0 F{self.speed}"
        )

    def _target_frame(self, position): # -> Literal("invalid") | set(k for k in self._FRAMES.keys()): # <- not sure if this will work, but would be nice for type hints in documentation.
        """
        Determines which frame contains the position.

        Parameters
        ----------
        position : list/np.ndarray
            [x, y, z] coordinate of point in 3D space

        Returns
        -------
        string
            name of frame. if none, returns "invalid"
        """
        for frame, lims in self._FRAMES.items():
            print(f"\tchecking frame {frame}")
            for idx, coord in enumerate(["x", "y", "z"]):
                v = position[idx]
                if (v < lims[f"{coord}_min"]) or (v > lims[f"{coord}_max"]):
                    print(f"\t\t{v} is outside bounds of {coord}-axis!")
                    continue
            print(f"\t\tThe position {position} is inside of frame {frame}")
            return frame
        return "invalid"
    
    def _transition_to_frame(self, target_frame):
        self._movecommand(
            x = self.position[0],
            y = self.position[1],
            z = self.TRANSITION_COORDINATES[2] - 1, # to be within bounds of opentrons
            speed = self.speed,
        )   # move in just z
        # nudge the gantry into the target frame
        x, y, z = self.TRANSITION_COORDINATES
        if target_frame == "opentrons":
            x -= self.TRANSITION_NUDGE
            self._ZLIM = self._constants["opentrons_limits"]["z_max"]
        else:
            x += self.TRANSITION_NUDGE
            self._ZLIM = self._constants["workspace_limits"]["z_max"]
        self._movecommand(
            x, y, z, speed = self.speed
        )
        print(f"\tGantry is not at the Transition Coordinates: \n\t[{x}, {y}, {z}]")
    
    def _move_below_opentrons_limits(self, x, y, z):
        self._movecommand(x, y, z, speed = self.speed)
    
    def premove(self, x, y, z, zhop = True):
        """
        Check to confirm that all target positions are valid

        Parameters
        ----------
        x : float
            destination x-coordinate
        y : float
            destination y-coordinate
        z : float
            destination z-coordinate
        zhop : bool, optional
            Move up a little in z before lateral motions to avoid gripper collisions, defaults to True.

        Returns
        -------
        tuple
            (x, y, z) position, if valid.

        Raises
        ------
        ValueError
            If target frame is not pre-defined, then the target position is invalid and we cannot move there.
        Exception
            If the gantry has not been homed, then we cannot move to controlled positions.
        """
        if self.position == [None, None, None]:
            raise Exception(
                "Stage has not been homed! Home with self.gohome() before moving please."
            )
        for idx, coord in enumerate([x, y, z]):
            if coord is None:
                coord = self.position[idx]
        # do we transition between opentrons/workspace? if so, handle it.
        target_frame = self._target_frame(position = [x, y, z])
        print(target_frame)
        cur_frames = list(self._FRAMES.keys())
        if target_frame not in cur_frames:
            print(f"frame {target_frame} is not in the defined frames!")
        if target_frame == "invalid": 
            raise ValueError(f"Coordinate {x}, {y}, {z} is invalid!")
        if self._currentframe != target_frame:
            print(f"\ttime to transition to a new frame")
            self._transition_to_frame(target_frame)
        return x, y, z
    
    def moveto(
            self,
            x: Optional[Union[float, List[float]]] = None,
            y: Optional[Union[float, List[float]]] = None,
            z: Optional[Union[float, List[float]]] = None,
            zhop: Optional[bool] = True,
            speed: Optional[float] = None,
    ):
        """Move the gantry to provided x, y, z coordinates

        Parameters
        ----------
        x : Optional[Union[float, List[float]]], optional
            If is a float, then is the x-coordinate to move to. 
            If is a list, then is the [x, y, z] coordinates to move to.
            By default is None.
        y : Optional[Union[float, List[float]]], optional
            y-coordinate to move to, by default None.
        z : Optional[Union[float, List[float]]], optional
            z-coordinate to move to, by default None.
        zhop : Optional[bool], optional
            Whether to move up in z a little to avoid potential gripper crash, by default True
        speed : Optional[float], optional
            movement speed, in mm/s for this motion, by default `self.speed`.

        Returns
        -------
        _type_
            _description_

        Raises
        ------
        ValueError
            _description_
        """
        try:
            if len(x) == 3:
                x, y, z = x #split 3 coordiantes into appropriate variables
        except:
            pass
        x, y, z = self.premove(x, y, z, zhop)
        if speed is None:
            speed = self.speed
        if (x == self.position[0]) and (y == self.position[1]):
            zhop = False #why zhop if no lateral movement
        if zhop:
            z_ceiling = max(self.position[2], z) + self.ZHOP_HEIGHT
            print(f"\tz_ceil: {z_ceiling}, ZLIM: {self._ZLIM}")
            z_ceiling = min(
                z_ceiling, self._ZLIM
            )
            print(f"\tmoving to z: {z_ceiling}")
            self.moveto(x, y, z_ceiling, zhop = False, speed = speed)
            print(f"\tmoving to x, y: {x}, {y}")
            self.moveto(x, y, z_ceiling, zhop = False, speed = speed)
            print(f"\tmoving to z: {z}")
            self.moveto(z = z, zhop = False, speed = speed)
        else:
            self._movecommand(x, y, z, speed)
    
    def movetoclear(self):
        """
        Moves the gantry to specified clear coordinates
        """
        self.moveto(self.CLEAR_COORDINATES)
    def movetoidle(self):
        """
        Moves the gantry to specified idle coordinates
        """
        self.moveto(self.IDLE_COORDINATES)
    
    def moverel(
            self,
            x: float = 0,
            y: float = 0,
            z: float = 0,
            zhop: bool = False, # is true in moveto(...) by default
            speed: float = None, 
        ):
        """
        Moves the gantry a specified distance along each of the x, y, and z axes irrespective of absolute coordinates
        
        note: zhop probably should match exactly with moveto(...) 
        Parameters
        ----------
        x : Optional[Union[float, List[float]]], optional
            If is a float, then is the x-coordinate to move to. 
            If is a list, then is the [x, y, z] coordinates to move to.
            By default is 0.
        y : Optional[Union[float, List[float]]], optional
            y-coordinate to move to, by default 0.
        z : Optional[Union[float, List[float]]], optional
            z-coordinate to move to, by default 0.
        zhop : Optional[bool], optional
            Whether to move up in z a little to avoid potential gripper crash, by default False
        speed : Optional[float], optional
            movement speed, in mm/s for this motion, by default 'self.speed'
        """
        try:
            if len(x) == 3:
                x, y, z = x
        except:
            pass
        x += self.position[0]
        y += self.position[1]
        z += self.position[2]
        self.moveto(x, y, z, zhop, speed)

    def _movecommand(
            self,
            x: float,
            y: float,
            z: float,
            speed: float,
    ) -> bool:
        """Internal command to execute a direct move from current location to new location."""
        if self.position == [x, y, z]:
            return True
        self._targetposition = [x, y, z]
        self.write(f"G0 X{x} Y{y} Z{z} F{speed}")
        return self._waitformovement()
    
    def _waitformovement(self):
        """
        Confirm that gantry has reached target position. returns False if 
        target position is not reached in time allotted by self.GANTRYTIMEOUT.
        """
        self.inmotion = True
        start_time = time.time()
        time_elapsed = time.time() - start_time
        self._handle.write(f"M400\n".encode()) #Halt compiling additional commands until previous command returns a response
        self._handle.write(f"M118 E1 FinishedMoving\n".encode()) # respond with keyword "FinishedMoving"
        reached_destination = False
        while (not reached_destination) and (time_elapsed < self.GANTRYTIMEOUT):
            time.sleep(self.POLLINGDELAY)
            while self._handle.in_waiting:
                line = self._handle.readline().decode("utf-8").strip()
                if line == "echo:FinishedMoving":
                    self.update()
                    if (
                        np.linalg.norm(
                            [
                                a - b for a, b in zip(self.position, self._targetposition)
                            ]
                        ) 
                        < self.POSITIONTOLERANCE
                    ):
                        reached_destination = True
                time.sleep(self.POLLINGDELAY)
        self.inmotion = ~reached_destination
        self.update()
        return reached_destination

class SocketCommunicator:
    """
    Communication using sockets to execute partially closed-loop motion logic for the Gantry.

    Designed for a particular use with a Duet 3 Mini 5+ Ethernet plus 2XD Expansion Board,
    to handle dual X-axis closed-loop stepper motors with HSS57 external drivers, and 
    open-loop Y and Z axis stepper motors driven by on-board TMC2209 drivers.
    """
    def __init__(self, ip: str = None, port: str = None):
        self._purpose = "Store relevant motion settings for the Gantry when using a Duet 3 Mini 5+ Ethernet control board for closed-loop dual X and open-loop Y, Z stepper motors"
        
        setup_constants(
            communicator_instance = self
        )


class WebsocketCommunicator:
    """
    Communication using websockets to execute partially closed-loop motion logic for the Gantry.

    Designed for a particular use with a Duet 3 Mini 5+ Ethernet plus 2XD Expansion Board,
    to handle dual X-axis closed-loop stepper motors with HSS57 external drivers, and 
    open-loop Y and Z axis stepper motors driven by on-board TMC2209 drivers.
    """
    def __init__(self):
        raise NotImplementedError("Communication over a websocket connection has not yet been developed. This method is for future generalization.")

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
        """
        Moves the gantry's coordinates to (0, 0, 0)
        """
        self._communicator.write("G28 X Y Z")
        self.update()
        self.movetoclear()
    
    def set_speed_percentage(
            self, 
            p: float = 80.0,
    ):
        self._communicator.set_speed_percentage(p = p)