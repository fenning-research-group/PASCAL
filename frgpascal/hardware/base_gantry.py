from dataclasses import dataclass
from abc import ABC, abstractmethod

from typing import Union
import serial
import socket
import websockets

@dataclass
class ConnectConfig:
    """dataclass for storing base properties used to set up communications."""
    POLLINGDELAY: float
    port: str | None
    ip: str | None

@dataclass
class MotionConfig:
    """dataclass for storing the base properties used for motion control"""
    # Motion Planning:
    position: tuple
    TRANSITION_COORDINATES: tuple
    CLEAR_COORDINATES: tuple
    IDLE_COORDINATES: tuple
    _targetposition: tuple
    _currentframe: str
    _ZLIM: float
    TRANSITION_NUDGE: float
    # Motion Execution:
    MAXSPEED: float
    MINSPEED: float
    ZHOP_HEIGHT: float
    in_use: bool


class BaseCommunicator(ABC):
    def __init__(self, config: ConnectConfig):
        self._config = config
    
    @property
    def config(self) -> ConnectConfig:
        return self._config

    # abstractmethods
    @abstractmethod
    def connect(self, port: str | None, ip: str | None) -> Union[serial.Serial, socket.socket, websockets.WebSocketClientProtocol]:
        """Setup the communication link."""
    @abstractmethod
    def write(self, msg) -> list:
        """Send a GCode command through the communicator, 
        split the response by line breaks, return as list"""
        raise NotImplementedError


class BaseMotionControl(ABC):
    
    # abstract properties

    # concrete properties

    # abstract methods
    @abstractmethod
    def set_defaults(self):
        """Sends set of GCode commands to ensure default configuration is properly set."""
        raise NotImplementedError
    
    # communal methods, same across all inheritors
    def _enable_steppers(self):
        """Send M17 GCode command to turn on the stepper motors"""
        self.write("M17")
    
    def _disable_steppers(self):
        """Send M18 GCode command to turn on the stepper motors"""
        self.write("M18")
    
    def set_speed_percentage(self, p):
        """Set the max allowed motion speed to a percentage 0-100% of max possible motion speed"""
        if (p < 0) or (p > 100):
            raise Exception("Speed must be set by a percentage value between 0-100!")
        self.speed = (p / 100) * (self.MAXSPEED - self.MINSPEED) + self.MINSPEED
