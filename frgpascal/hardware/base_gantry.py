from dataclasses import dataclass, fields, _MISSING_TYPE, field
from abc import ABC, abstractmethod
from enum import Enum
import time
import re
from typing import Union, Set, List, Optional, Tuple, Generic, TypeVar
import serial
import socket
import websockets
import numpy as np


# AllowedFrames = Literal["invalid", "workspace", "opentrons"]
# Motion / Communication Exceptions:
class HomingError(Exception):
    """Exception raised if a moving tool has not yet been homed."""
    def __init__(
            self, 
            message = "Uh-oh, Looks like the Gantry has not been homed! Be sure to run the .gohome() method first."
    ):
        self.message = message
        super().__init__(self.message) # pass the exception message through to the base Exception

class FrameError(Exception):
    """Exception raised if the target coordinate is not in a pre-defined frame of reference."""
    def __init__(
        self,
        position: tuple,
    ):
        self.message = f"Coordinate [{position[0]}, {position[1]}, {position[2]}] is not within the defined frames!"
        super().__init__(self.message)

class TargetError(Exception):
    """Exception raised if the target coordinate is not given to the `premove()` method of a class inheritor of BaseMotionControl"""
    def __init__(self):
        super().__init__("Cannot move to a coordinate that is [None, None, None]!")


@dataclass
class ConnectConfig:
    """dataclass for storing base properties used to set up communications."""
    POLLINGDELAY: float = 0.05
    port: Union[str, None] = ""
    ip: Union[str, None] = ""

    def __post_init__(self):
        for field in fields(self):
            # If there is a default and the value of the field is missing, then we can assign a value
            if not isinstance(field.default, _MISSING_TYPE) and getattr(self, field.name) is None:
                setattr(self, field.name, field.default)

@dataclass
class MotionConfig:
    """dataclass for storing the base properties used for continuous motion control"""
    # Motion Planning:
    position: Union[tuple, list] = field(default_factory = list)
    TRANSITION_COORDINATES: Union[tuple, list] = field(default_factory = list)
    CLEAR_COORDINATES: Union[tuple, list] = field(default_factory = list)
    IDLE_COORDINATES: Union[tuple, list] = field(default_factory = list)
    _targetposition: tuple = field(default_factory = tuple)
    _currentframe: str = ""
    _ZLIM: float = 1
    TRANSITION_NUDGE: float = 1
    # Motion Execution:
    MAXSPEED: float = 1
    MINSPEED: float = 1
    ZHOP_HEIGHT: float = 1
    in_use: bool = True
    GANTRYTIMEOUT: float = 1

    def __post_init__(self):
        for field in fields(self):
            # If there is a default and the value of the field is missing, then we can assign a value
            if not isinstance(field.default, _MISSING_TYPE) and getattr(self, field.name) is None:
                setattr(self, field.name, field.default)
@dataclass
class GridConfig(MotionConfig):
    """dataclass for storing the base properties used for discrete motion control."""
    grid_spacing_x: float = 1
    grid_spacing_y: float = 1
    grid_spacing_z: float = 1

ConfigVar = TypeVar("ConfigVar", bound = MotionConfig)

class Frames(str, Enum):
    """Enumeration of subspaces of the workspace"""
    Workspace = "workspace"
    Opentrons = "opentrons"
    Invalid = "invalid"

class BaseCommunicator(ABC):
    def __init__(self, config: ConnectConfig = ConnectConfig()):
        self._config = config
    
    @property
    def config(self) -> ConnectConfig:
        return self._config

    # abstractmethods
    @abstractmethod
    def connect(self, port: Union[str, None], ip: Union[str, None]) -> Union[serial.Serial, socket.socket, websockets.WebSocketClientProtocol]:
        """Setup the communication link."""
        raise NotImplementedError
    @abstractmethod
    def write(self, msg) -> list:
        """Send a GCode command through the communicator, 
        split the response by line breaks, return as list"""
        raise NotImplementedError
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect, delete the communication link."""
        raise NotImplementedError
    
    @abstractmethod
    def _send_echo(self, stop_moving: bool = True):
        """Sends an echo command to the communicator."""
        raise NotImplementedError
    
    @abstractmethod
    def _search_for_echo(self):
        """Search for the most recent echo response from the communicator."""
        raise NotImplementedError
    
    @abstractmethod
    def _ready_to_talk(self) -> bool:
        """Checks if self._handle has bytes available for reading."""
        raise NotImplementedError


class BaseMotionControl(ABC, Generic[ConfigVar]):
    def __init__(self, config: ConfigVar, communicator: BaseCommunicator):
        self._config = config
        self._speed = self._config.MAXSPEED
        # self._position = self._config.position
        self._comms = communicator
    # abstract properties
    @property
    def speed(self) -> float:
        return self._speed
    
    @speed.setter
    def speed(self, value):
        self._speed = value
        self._comms.write(
            msg = f"G0 F{value}"
        )

    @property
    def position(self) -> List:
        return self._config.position
    
    @position.setter
    def position(self, pos):
        print("PRE-SET")
        print(pos)
        # print(f"._position: {self._position}")
        print(f"._config.position: {self._config.position}")
        self._config.position = pos
        print("POST-SET")
        print(pos)
        # print(f"._position: {self._position}")
        print(f"._config.position: {self._config.position}")

    # concrete properties
    @property
    def config(self) -> MotionConfig:
        return self._config

    # abstract methods
    @abstractmethod
    def set_defaults(self):
        """Sends set of GCode commands to ensure default configuration is properly set."""
        raise NotImplementedError
    
    # communal methods, same across all inheritors

    def gohome(self):
        self._comms.write("G28 X Y Z")
        self.update()
        self.movetoclear()
    def _enable_steppers(self):
        """Send M17 GCode command to turn on the stepper motors"""
        self._comms.write("M17")
    
    def _disable_steppers(self):
        """Send M18 GCode command to turn on the stepper motors"""
        self._comms.write("M18")
    
    def set_speed_percentage(self, p):
        """Set the max allowed motion speed to a percentage 0-100% of max possible motion speed"""
        if (p < 0) or (p > 100):
            raise Exception("Speed must be set by a percentage value between 0-100!")
        self.speed = (p / 100) * (self.MAXSPEED - self.MINSPEED) + self.MINSPEED
    
    def _target_frame(self, position: Union[tuple, list]) -> Set[Frames]: # validate that the AllowedFrames are the only options defined for this codebase.
        """
        Determine which frame contains the position.

        Parameters
        ----------
        position : Union[tuple, list]
            [x, y, z] coordinate of point in rectangular space.

        Returns
        -------
        Set[Frames]
            name of frame. if none, returns "invalid".
        """
        for frame, lims in self.config._FRAMES.items():
            print(f"\tchecking frame {frame}")
            for idx, coord in enumerate(["x", "y", "z"]):
                v = position[idx]
                if v is not None:
                    if (v < lims[f"{coord}_min"]) or (v > lims[f"{coord}_max"]):
                        print(f"\t\t{v} is outside bounds of {coord}-axis!")
                        continue
            print(f"\t\tThe position {position} is inside of frame {frame}")
            return frame
        return "invalid"
    
    def _transition_to_frame(self, target_frame: Set[Frames]) -> None:
        """
        Gently move the gantry between frames near the transition coordinate

        Parameters
        ----------
        target_frame : Set[Frames]
            The frame to transition into.
        """
        x, y, z = self.config.TRANSITION_COORDINATES
        if target_frame == "opentrons":
            x -= self.config.TRANSITION_NUDGE
        else:
            x += self.config.TRANSITION_NUDGE
        self.config._ZLIM = self.config._FRAMES[f"{target_frame}"]["z_max"]
        self._movecommand(
            x, y, z, speed = self.speed
        )


    def update(self):
        found_coordinates = False
        while not found_coordinates:
            output = self._comms.write("M114") # get current position
            for line in output:
                if line.startswith("X:"):
                    x = float(re.findall(r"X:(\S*)", line)[0])
                    y = float(re.findall(r"Y:(\S*)", line)[0])
                    z = float(re.findall(r"Z:(\S*)", line)[0])
                    found_coordinates = True
                    break

            self.config.position = [x, y, z]
            self.config._currentframe = self._target_frame(self.config.position)
            print(f"\t\t{self._currentframe}")
            self.config._ZLIM = self.config._FRAMES[self.config._currentframe]["z_max"]

    def _transform_coordinates(
            self,
            x: float,
            y: float,
            z: float,
    ):
        """transform provided coordinates into alternative basis.

        Identity transform at base, for upgrading within inheriting class.

        Parameters
        ----------
        x : float
            x_coordinate, in mm
        y : float
            y_coordinate, in mm
        z : float
            z_coordinate, in mm

        Returns
        -------
        tuple
            target coordinates for this motion.
        """
        return x, y, z

    def premove(
            self, 
            x: float, 
            y: float, 
            z: float, 
    ) -> tuple:
        """
        Check to confirm that all target positions are valid.

        Parameters
        ----------
        x : float
            target coordinate along x-axis to validate
        y : float
            target coordinate along x-axis to validate
        z : float
            target coordinate along x-axis to validate
        
        Returns
        -------
        tuple
            (x, y, z) position, if valid.
        
        Raises
        ------
        HomingError
            If the gantry has not been homed, then we cannot move to controlled positions.
        """
        if self.config.position == [None, None, None]:
            raise HomingError()
        # do we transition between opentrons/workspace? if so, handle it.
        target_frame = self._target_frame(position = (x, y, z))
        # cur_frames = list(self.config._FRAMES.keys())
        # if target_frame not in cur_frames:
            # print(f"frame {target_frame} is not in the defined frames!")
        if target_frame == "invalid":
            raise FrameError()
        if self.config._currentframe != target_frame:
            print(f"\ttime to transition to a new frame")
            self._transition_to_frame(target_frame)
        return x, y, z
    
    def moveto(
            self,
            x: Optional[Union[float, List[float]]] = None,
            y: Optional[float] = None,
            z: Optional[float] = None,
            zhop: Optional[bool] = True,
            speed: Optional[float] = None,
    ):
        """Move the gantry to provided x, y, z coordinates.

        Parameters
        ----------
        x : Optional[Union[float, List[float]]], optional
            If is a float, then is the x-coordinate to move to.
            If is a list, then is the [x, y, z] coordinate to move to.
            Defaults to None.
        y : Optional[float], optional
            y-coordinate to move to, defaults to None.
        z : Optional[float], optional
            z-coordinate to move to, defaults to None
        zhop : Optional[bool], optional
            Whether to jog upwards in z-axis at begin/end of move,
            to avoid crashing the gripper head. Defaults to True.
        speed : Optional[float], optional
            Speed to overwrite default for this move only, defaults to None.
        
        Raises
        ------
        TargetError
            If all of {x, y, z} are None, then there is no defined coordiante to move to.
        """
        try:
            if len(x) == 3:
                y = x[1]
                z = x[2]
                x = x[0]
            # x_, y_, z_ = tuple(x)
            # x, y, z = tuple(x_, y_, z_)
        except:
            pass
        if (x is None) and (y is None) and (z is None):
            raise TargetError()
        print(x, y, z)
        # if len(x) == 3:
        x, y, z = self._transform_coordinates(x, y, z)
        x, y, z = self.premove(x, y, z)
        if (x == self.config.position[0]) and (y == self.position[1]):
            zhop = False #why zhop if no lateral movement
        if zhop:
            z_ceiling = max(self.config.position[2], z) + self.config.ZHOP_HEIGHT
            z_ceiling = min(z_ceiling, self.config._ZLIM)
            self.moveto(x, y, z_ceiling, zhop = False, speed = speed)
            self.moveto(x, y, z_ceiling, zhop = False)
            self.moveto(z = z, zhop = False, speed = speed)
        else:
            self._movecommand(x, y, z, speed)
    
    def movetoclear(self):
        self.moveto(self.config.CLEAR_COORDINATES)
    def movetoidle(self):
        self.moveto(self.config.IDLE_COORDINATES)
    def moverel(
            self,
            x: Optional[float] = 0,
            y: Optional[float] = 0,
            z: Optional[float] = 0,
            zhop: Optional[bool] = False,
            speed: Optional[float] = None,
    ):
        """Move relative to the current position.

        Parameters
        ----------
        x : Optional[float], optional
            mm to move along x-axis, defaults to 0 mm.
        y : Optional[float], optional
            mm to move along y-axis, defaults to 0 mm.
        z : Optional[float], optional
            mm to move along z-axis, defaults to 0 mm.
        zhop : Optional[bool], optional
            Whether to jog upwards in z-axis at begin/end of move,
            to avoid crashing the gripper head. Defaults to False.
        speed : Optional[float], optional
            Speed to overwrite default for this move only, defaults to None.
        """
        x += self.config.position[0]
        y += self.config.position[1]
        z += self.config.position[2]
        self.moveto(x, y, z, zhop, speed)
    
    def _movecommand(
        self,
        x: float,
        y: float,
        z: float,
        speed: Optional[float] = None,
    ) -> bool:
        """Send a controlled linear motion command to the communicator

        Parameters
        ----------
        x : Optional[float], optional
            mm to move along x-axis, defaults to 0 mm.
        y : Optional[float], optional
            mm to move along y-axis, defaults to 0 mm.
        z : Optional[float], optional
            mm to move along z-axis, defaults to 0 mm.
        speed : Optional[float], optional
            Speed to overwrite default for this move only, defaults to None.
        
        Returns
        -------
        bool
            _description_
        """
        if [p == c for p, c in zip(self.config.position, [x, y, z])]:
            return True
        reset_speed = self.speed
        if speed is None:
            speed = self.speed
            reset_speed = None
        self.config._targetposition = [x, y, z]
        self._comms.write(f"G1 X{x} Y{y} Z{z} F{speed}")
        done_moving = self._waitformovement()
        if reset_speed is not None:
            self._comms.write(f"G0 F{reset_speed}")
        return done_moving

    def _waitformovement(self) -> bool:
        """Confirm that the gantry has reached target position.

        Returns
        -------
        bool
            Returns False if target position is not reached
            in the time allotted by self.config.GANTRYTIMEOUT
        """
        self.config.in_motion = True
        start_time = time.time()
        time_elapsed = time.time() - start_time
        self._comms.write("M400")
        self._send_echo(stop_moving = True)

        reached_destination = False
        while (not reached_destination) and (time_elapsed < self.config.GANTRYTIMEOUT):
            print("Are we there yet?")
            time.sleep(self._comms.config.POLLINGDELAY)
            yapping = self._comms._ready_to_talk()
            while yapping:
                print("Ready to talk")
                done_move = self._comms._search_for_echo()
                if done_move:
                    self.update()
                    if (
                        np.linalg.norm(
                            [
                                a - b 
                                for a, b in zip(
                                    self.config.position,
                                    self.config._targetposition
                                )
                            ]
                        )
                    ):
                        reached_destination = True
                        yapping = False
                time.sleep(self._comms.config.POLLINGDELAY)
        self.config.in_motion = ~reached_destination
        self.update()
        return reached_destination

class DiscreteMotionControl(BaseMotionControl[GridConfig]):

    def _transform_coordinates(self, x: float, y: float, z: float) -> Tuple[int, int, int]:
        """Map provided target position into discrete grid coordinates:

        Parameters
        ----------
        x : float
            target x_coordinate, in mm.
        y : float
            target y_coordinate, in mm.
        z : float
            target z_coordinate, in mm.

        Returns
        -------
        Union[Tuple[int, int, int], List[int, int, int]]
            The nearest grid coordinates for the target coordinates.
        """
        if x is not None:
            x = int(round(x / self.config.grid_spacing_x)) * self.config.grid_spacing_x
        if y is not None:
            y = int(round(y / self.config.grid_spacing_y)) * self.config.grid_spacing_y
        if z is not None:
            z = int(round(z / self.config.grid_spacing_z)) * self.config.grid_spacing_z
        return (x, y, z)