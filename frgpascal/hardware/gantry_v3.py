import serial
import socket
import websockets

import time
import re
import numpy as np
import sys
from PyQt5.Widgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton
import yaml
import os
from functools import partial

from frgpascal.hardware.base_gantry import BaseCommunicator, BaseMotionControl, DiscreteMotionControl
from frgpascal.hardware.helpers import get_port

try:
    from typing import Literal
except:
    from typing_extensions import Literal
from typing import Union, List, Optional, Set

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader = yaml.FullLoader)

AllowedFrames = Literal["invalid", "workspace", "opentrons"]

def setup_constants(obj_instance, attr_info):
    """Scrapes the hardware constants.
    
    Adds attrs from attr_info into the configuration of the provided obj_instance
    
    Parameters
    ----------
    obj_instance : Union[BaseMotionControl, DiscreteMotionControl, BaseCommunicator, SerialCommunicator, SocketCommunicator, WebsocketCommunicator]

    attr_info : List[Tuple]
        Each element of attr_info should be of the form (str(attribute name), Union[str(key for relevant value in yaml), (default value if not in yaml)])
    """
    for ati in attr_info:
        name_, val_ = ati
        if isinstance(val_, dict):
            val = {k: obj_instance._constants[v] for k, v in val_.items()}
        elif isinstance(val_, str):
            val = obj_instance._constants[val_]
        else:
            val = val_
        setattr(
            obj = obj_instance.config,
            name = name_,
            value = val
        )

def setup_motion_constants(controller_instance: Union[BaseMotionControl, BTTSKRMiniE3_MotionControl, DiscreteMotionControl, Duet3Mini5Plus_MotionControl]):
    """
    Scrape the hardware constants for the given controller_instance.

    Adds common attributes for motion control into the controller config.
    Parameters
    ----------
    controller_instance : 
        _description_
    """
    attr_info = [
        # (name, constants key)
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
    if isinstance(controller_instance, DiscreteMotionControl) or isinstance(controller_instance, Duet3Mini5Plus_MotionControl):
        for axis in ["x", "y", "z"]:
            attr_info.append(
                (f"grid_spacing_{axis}", {"grid_spacing": f"{axis}_axis"})
            )
    setup_constants(
        obj_instance = controller_instance,
        attr_info = attr_info
    )

def setup_connect_constants(communicator_instance: Union[BaseCommunicator, SerialCommunicator, SocketCommunicator, WebsocketCommunicator]):
    """
    Scrape the hardware constants for the given communicator_instance.

    Add common attributes for hardware communications into the communicator config.
    Parameters
    ----------
    communicator_instance : _type_
        _description_
    """
    attr_info = [
        # (name, constants key)
        ("POLLINGDELAY", "pollingrate")
    ]
    if isinstance(communicator_instance, SerialCommunicator):
        attr_info.append(
            ("port", {"device_identifiers": "port"})
        )
        attr_info.append(
            ("device_identifiers", "device_identifiers")
        )
    elif isinstance(communicator_instance, SocketCommunicator):
        attr_info.append(
            ("ip", {"device_identifiers": "ip"})
        )
        attr_info.append(
            ("device_identifiers", "device_identifiers")
        )
        attr_info.append(
            ("_connected_network_devices", {})
        )
    #TODO: handle special cases
    # spec_attrs = []
    # if isinstance(communicator_instance, SerialCommunicator):
    #     # add special constants for the SerialCommunicator, if they have not yet been defined as attributes
    # elif isinstance(communicator_instance, SocketCommunicator):
    #     # add special constants for just the SocketCommunicator
    # elif isinstance(communicator_instance, WebsocketCommunicator):

    setup_constants(
        obj_instance = communicator_instance,
        attr_info = attr_info
    )



class SerialCommunicator(BaseCommunicator):
    """Communication via serial connection to execute commands.

    Parameters
    ----------
    BaseCommunicator : _type_
        _description_
    """

    def __init__(self, port: str = None):
        self._constants = constants["gantry_v2"]["serial_connection"]
        setup_connect_constants(
            communicator_instance = self
        )
        if port is None:
            self.config.port = get_port(
                device_identifiers = self.config.device_identifiers
            )
        else:
            self.config.port = port
        self._connect()

    def connect(self) -> serial.Serial:
        self._comms = serial.Serial(port = self.config.port, timeout = 1, baudrate = 115200)
    
    def disconnect(self):
        self._comms.close()
        del self._comms
    
    def _ready_to_talk(self):
        return self._comms.in_waiting
    
    def _send_echo(self, stop_moving = True):
        if not stop_moving:
            raise NotImplementedError("frgpascal.hardware.gantry.SerialCommunicator is only configured to send echos regarding motion control.")
        echo_command = "M118 E1 FinishedMoving"
        self._comms.write(echo_command)
    
    def _search_for_echo(self, stop_moving = True):
        return self._comms.readline().decode("utf-8").strip()
    
    def write(self, msg: str) -> list[str]:
        self._comms.write(
            f"{msg}\n".encode()
        )
        time.sleep(self.config.POLLINGDELAY)
        output = []
        while self._comms.in_waiting:
            line = self._comms.readline().decode("utf-8").strip()
            if line != "ok":
                output.append(line)
            time.sleep(self.config.POLLINGDELAY)
        return output

class SocketCommunicator(BaseCommunicator):
    """Communication via socket connection to execute commands.
    """

    def __init__(self):
        self._constants = constants["gantry_v2"]["socket_connection"]
        setup_connect_constants(
            communicator_instance = self
        )
        self.connect()

    def connect(self) -> socket.socket:
        """Connect to a socket communication."""
        if self.config.ip in self.config._connected_network_devices:
            print(f"The device at {self.config.ip} is already connected!")
            return self.config._connected_network.devices[self.config.ip]
        # Can we talk with the device? (deprecated)
        # if not self.ping_device(ip = self.ip):
            # raise ValueError(f"Device at {self.config.ip}:{self.config.port} is not reachable (ping failed)!")
        try:
            for port in ["23", "21", "80"]:
                try:
                    print(f"Trying to connect to device at {self.config.ip}:{port}...")
                    self._handle = socket.create_connection((self.config.ip, port), timeout = 5)
                    if port == "21":
                        print(f"\tDevice conneted over OTHER type connection")
                    elif port == "23":
                        print(f"\tDevice connected over TCP type connection")
                    elif port == "80":
                        print(f"\tDevice connected over HTTP type connection")
                    self.config.port = port
                    break
                except Exception as e:
                    print(f"\t Connecting at {self.config.ip}:{port} failed \n\t{e}")
                    self.disconnect()
            self.config._connected_network_devices[self.config.ip] = self._handle
        except Exception as e:
            raise ValueError(f"Failed to connect to Duet at {self.config.ip} for any ports [23, 21, 80]!\n{e}")
    
    def disconnect(self):
        """Disconnect the socket communication."""
        self._handle.close()
        del self._handle
    
    def send_gcode(self, command, homing = True):
        """
        Send a G-code command to a device over the SocketCommunicator._handle socket object.

        Parameters
        ----------
        command : str
            The G-Code to send
        homing : bool, optional
            If True, removes timeout to collect response from socket (Default setting)
            If False, sets timeout for response from socket to 30 seconds
        """
        if not self._handle:
            raise ValueError("socket is not connected, be sure to run .connect() first!")
        self._handle.sendall((command + "\n").encode("utf-8"))
        bytes_to_receive = 1024
        if homing:
            self._handle.settimout(None)
            response_0 = self._handle.recv(bytes_to_receive).decode("utf-8")
            response = response_0.split()
            self._handle.settimeout(30)
        else:
            response = [self._handle.recv(bytes_to_receive).decode("utf-8").strip()]
        return response
    
    def write(self, msg: str) -> list[str]:
        response = self.send_gcode(command = msg)
        return response
    
    def _ready_to_talk(self) -> bool:
        return True
    
    def _send_echo(self, stop_moving = True):
        if not stop_moving:
            raise NotImplementedError("frgpascal.hardware.gantry.SerialCommunicator is only configured to send echos regarding motion control.")
        echo_command = 'M118 S"FinishedMoving"'
        self._handle.sendall((echo_command + "\n").encode("utf-8"))
    
    def _search_for_echo(self):
        return self._handle.recv(1024).decode("utf-8").strip()

class WebCommunicator(BaseCommunicator):
    def __init__(self):
        raise NotImplementedError("Support for websockets connection is planned for future development.")

class BTTSKRMiniE3_MotionControl(BaseMotionControl):

    def __init__(self, communicator: SerialCommunicator):
        self._constants = constants["gantry_v2"]["serial_connection"]
        setup_motion_constants(
            controller_instance = self
        )
        super().__init__(config = self.config, communicator = communicator)


    def set_defaults(self):
        self.write("M501")   # load defaults from EEPROM
        self.write("G90")   # absolute coordinate system
        self.write("M92 X53") # set steps/mm if using 3mm pitch belts om x-axis
        self.write(
            "M906 X800 Y800 Z800 E1"
        )   # set max steppmer RMS currents (mA) per axis. E = extruder, unused to set low
        self.write(
            f"M203 x{self.config.MAXSPEED} Y{self.config.MAXSPEED} Z20.00"
        )   # set max speeds, mm/s. Z is hardcoded, limited by lead screw hardware
        self.write(
            "M84 S0"
        )   # disable stepper timeout, steppers remain engaged all the time
        self.set_speed_percentage(80)

class Duet3Mini5Plus_MotionControl(DiscreteMotionControl):

    def __init__(self, communicator: SocketCommunicator):
        self._constants = constants["gantry_v2"]["socket_connection"]
        setup_motion_constants(
            controller_instance = self
        )
        super().__init__(config = self.config, communicator = communicator)

    def set_defaults(self):
        self.write("M501")
        self.write("G90")

from frgpascal.hardware.gantry import GantryGUI #TODO: Extend GantryGUI to work for a discrete coordinate basis.

class NewGantry:
    def __init__(self, communicator: Union[SerialCommunicator, SocketCommunicator], controller: Union[BTTSKRMiniE3_MotionControl, Duet3Mini5Plus_MotionControl]):
        comms = communicator()
        controls = controller(comms)
        print("Gantry ready to go!")
    
    def gui(self):
        GantryGUI(gantry = self)
