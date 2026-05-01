"""This file contains the core logic of handling a modality of motion control in JVBot.

Classes
-------
ConnectConfig: Type[BaseConstantsConfig]
    Dataclass container to hold hardwareconstants relevant to some form of hardware communication.
MotionConfig: Type[BaseConstantsConfig]
    Dataclass container to hold hardwareconstants relevant to some form of gantry motion control.
GridConfig: Type[MotionConfig]
    Wrapper of MotionConfig to also include hardwareconstants relevant to gantry-space 3D discrete mappings.
Frames: Type[Enum]
    Enumeration class to match pre-allocation gantry coordinate sets in partitions.

BaseCommunicator: Type[abc.ABC]
    Base class to define fundamental hardware communication logic
SerialCommunicator: Type[BaseCommunicator]
    Wrapper of BaseCommunicator specialized to interface with BigTreeTech SKR Mini E3 V2.0 motion control 
    over a wired USB connection.
SocketCommunicator: Type[BaseCommunicator]
    Wrapper of BaseCommunicator specialized to interface with a Duet 3 Mini 5+ Ethernet motion control 
    board over a wired Ethernet TCP connection.
WiFiCommunicator: Type[SocketCommunicator]
    Wrapper of SocketCommunicator specialized to interface with a Duet 3 Mini 5+ WiFi motion control
    board over the wireless connection.
FakeCommunicator: Type[SocketCommunicator]
    Wrapper of SocketCommunicator designed to simulate Duet 3 Mini 5+ motion control board communications
    for testing of non-communication errors of the gantry module.

BaseMotionControl: Type[abc.ABC]
    Base class to define fundamental cartesian X,Y,Z motion logic over g-code commands to motor drivers.
DiscreteMotionControl: Type[BaseMotionControl]
    Wrapper of BaseMotionControl to handle conversion of continuous 3-space into discrete 3-space to 
    minimize accumulation of positional errors of open-loop stepper motors in long-term operation.
BTTSKRMiniE3_MotionControl: Type[BaseMotionControl]
    Wrapper of BaseMotionControl to implement the SerialCommunicator with the g-code logic
Duet3Mini5PlusEthernet_MotionControl: Type[DiscreteMotionControl]:
    Wrapper of DiscreteMotionControl to implement the SocketCommunicator with the G-code logic

Errors
------
HomingError:
    Exception raised if the gantry has not been homed before a motion is attempted.
FrameError:
    Exception raised if the gantry needs to transition between coordinate frames of reference.
    e.g., if some region of the gantry's maximum range of motion has geometric constraints.
TargetError:
    Exception raised if the positional target of the move command is outside of the 
    allowed domain of gantry motion.
"""

import serial
import socket
import websockets

import time
import re
import numpy as np
import sys
# from PyQt5.Widgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton
import yaml
import os
from functools import partial

from frgpascal.hardware.base_gantry import BaseCommunicator, BaseMotionControl, DiscreteMotionControl, MotionConfig, GridConfig
from frgpascal.hardware.helpers import get_port, get_qapp

try:
    from typing import Literal
except:
    from typing_extensions import Literal
from typing import Union, List, Optional, Set

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader = yaml.FullLoader)

AllowedFrames = Literal["invalid", "workspace", "opentrons"]



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
        if "FinishedMoving" in self._comms.write(""):
            return True
        else:
            return False
        # return self._comms.readline().decode("utf-8").strip()
    
    def write(self, msg: str) -> List[str]:
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
        super().__init__()
        setup_connect_constants(
            communicator_instance = self
        )
        # self.connect()

    def connect(self) -> socket.socket:
        """Connect to a socket communication."""
        if self.config.ip in self.config._connected_network_devices:
            print(f"The device at {self.config.ip} is already connected!")
            return self.config._connected_network_devices[self.config.ip]
        # Can we talk with the device? (deprecated)
        # if not self.ping_device(ip = self.ip):
            # raise ValueError(f"Device at {self.config.ip}:{self.config.port} is not reachable (ping failed)!")
        try:
            for port in ["23", "21", "80"]:
                try:
                    print(f"Trying to connect to device at {self.config.ip}:{port}...")
                    self._handle = socket.create_connection((self.config.ip, port), timeout = 5)
                    # Clear any stale data from the socket connected. e.g., partially executed Gantry.moveto() commands which could crash gripper.
                    self._handle.setblocking(False)
                    try:
                        while True:
                            data = self._handle.recv(4096)
                            if not data:
                                break
                    except (BlockingIOError, socket.error):
                        pass # Buffer is now empty
                    self._handle.setblocking(True)
                    # Now that Buffer is empty, do a quick restart of the Duet board's task execution queue.
                    # self._handle.sendall(b"M999\n")
                    print("Resetting Duet to initial state!")
                    time.sleep(15)
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
        try:
            self.config._connected_network_devices.pop(self.config.ip)
        except KeyError:
            self.config._connected_network_devices = {}
        del self._handle
    
    def send_gcode(self, command, homing = False):
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
        print(f"\tHOMING: {homing}")
        if not self._handle:
            raise ValueError("socket is not connected, be sure to run .connect() first!")
        self._handle.sendall((command + "\n").encode("utf-8"))
        bytes_to_receive = 1024
        if homing:
            self._handle.settimeout(None)
            response_0 = self._handle.recv(bytes_to_receive).decode("utf-8")
            response = response_0.strip()
            self._handle.settimeout(30)
        else:
            response = self._handle.recv(bytes_to_receive).decode("utf-8").strip()
            print(response)
            response_0 = None
        return response_0, response
    
    def write(self, msg: str, bootup: bool = False) -> List[str]:
        response_0, response = self.send_gcode(command = msg, homing = not bootup)
        if response_0 is None:
            response_0 = response
        return response_0
    
    def _ready_to_talk(self) -> bool:
        return True
    
    def _send_echo(self, stop_moving = True):
        if not stop_moving:
            raise NotImplementedError("frgpascal.hardware.gantry.SerialCommunicator is only configured to send echos regarding motion control.")
        echo_command = 'M118 S"FinishedMoving"'
        self._handle.sendall((echo_command + "\n").encode("utf-8"))
    
    def _search_for_echo(self):
        resp, resp1 = self.send_gcode("")
        if resp is None:
            resp = resp1
        if isinstance(resp, str):
            resp = [resp]
        print(f"resp[0]: {resp[0]}")
        print(f"{'FinishedMoving' in resp}, {'FinishedMoving'==resp[0]}, {type(resp[0])} ")
        aaa = resp[0].strip()
        Cond1 = 'FinishedMoving' in aaa
        Cond2 = 'FinishedMoving' == aaa
        print(f"aaa: {aaa}, {Cond1}, {Cond2}")
        bbb = [r.strip() for r in resp]
        ccc = resp[0].split()
        print(f"bbb: {bbb}")
        print(f"ccc: {ccc}")
        ddd = [c.strip() for c in ccc]
        print(f"ddd: {ddd}")
        if "FinishedMoving" in ddd:
            return True
        else:
            return False
        # return self._handle.recv(1024).decode("utf-8").strip()

class FakeCommunicator(SocketCommunicator):
    def connect(self):
        self._handle = None
    def disconnect(self):
        print("Disconnected")
        # del self._handle
    def send_gcode(self, command, homing = True):
        # return ["M114 X0.00 Y0.00 Z0.00"]
        return ["M114 X450.00 Y150.00 Z33.00"]
    def _send_echo(self, stop_moving = True):
        return "echo sent"
    def _search_for_echo(self):
        return "FinishedMoving"

class WebCommunicator(BaseCommunicator):
    def __init__(self):
        raise NotImplementedError("Support for websockets connection is planned for future development.")

class BTTSKRMiniE3_MotionControl(BaseMotionControl):

    def __init__(self, communicator: SerialCommunicator):
        self._constants = constants["gantry_v2"]["serial_connection"]
        self._config = MotionConfig()
        setup_motion_constants(
            controller_instance = self
        )
        super().__init__(config = self._config, communicator = communicator)

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
        self._config = GridConfig()
        setup_motion_constants(
            controller_instance = self
        )
        super().__init__(config = self._config, communicator = communicator)

    def set_defaults(self):
        self._comms.write("M501")
        self._comms.write("G90")

    def update(self, bootup = False):
        found_coordinates = False
        print("UPDATING")
        while not found_coordinates:
            output = self._comms.write("M114", bootup = bootup) # get current position
            if isinstance(output, str):
                output = [output]
            for line in output:
                print(line)
                if line.startswith("X:"):
                    x = float(re.findall(r"X:(\S*)", line)[0])
                    y = float(re.findall(r"Y:(\S*)", line)[0])
                    z = float(re.findall(r"Z:(\S*)", line)[0])
                    found_coordinates = True
                    break

        self.position = [
            round(x, 1), round(y, 1), round(z, 1)]
        self.config._currentframe = self._target_frame(self.position)
        print(f"\t\t{self.config._currentframe}")
        self.config._ZLIM = self.config._FRAMES[self.config._currentframe]["z_max"]


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
        # print(ati)
        # print(obj_instance._config)
        name_, val_ = ati
        print(name_, val_)
        # print(obj_instance._constants)
        if isinstance(val_, dict):
            if "device_identifiers" == name_:
                val = {k: obj_instance._constants[k][v] for k, v in val_.items()}
            elif "grid_spacing" in name_ or "ip" in name_:
                print(val_)
                vd = {k: obj_instance._constants[k][v] for k, v in val_.items()}
                print(vd)
                vv = [v for k, v in vd.items()][0]
                print(type(vv), vv)
                val = vv
            elif ("_" in name_) and (not val_):
                print(f"\t{name_}\t{val_}")
                val = {k: obj_instance._constants[v] for k, v in val_.items()}
            elif ("_" in name_) and (val_) and ("FRAMES" not in name_):
                print(name_, val_)
                val = {}
            elif ("FRAMES" in name_):
                print(val_)
                val = {k: obj_instance._constants[v] for k, v in val_.items()}
            else:
                val = {k: obj_instance._constants[k][v] for k, v in val_.items()}
        elif isinstance(val_, str):
            val = obj_instance._constants[val_]
        else:
            val = val_
        # print(name_, val)
        setattr(
            obj_instance._config,
            name_,
            val
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
                # (f"grid_spacing_{axis}", f"grid_spacing_{axis}")
            )
    setup_constants(
        obj_instance = controller_instance,
        attr_info = attr_info
    )

def setup_connect_constants(
    communicator_instance: Union[
        BaseCommunicator, SerialCommunicator, SocketCommunicator, 
        # WebsocketCommunicator
    ]
):
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


from frgpascal.hardware.gantry import GantryGUI #TODO: Extend GantryGUI to work for a discrete coordinate basis.
from frgpascal.hardware.gantry_gui import GantryControlWidget, BestGantryGUI

class NewGantry:
    """The Gantry control object for interfacing with the other control objects of PASCAL.

    Primarily a wrapper around the MotionControl objects, for converting the expected Gantry methods
    into the backend MotionControl methods.
    """
    def __init__(self, communicator: Union[SerialCommunicator, SocketCommunicator, FakeCommunicator], controller: Union[BTTSKRMiniE3_MotionControl, Duet3Mini5Plus_MotionControl], simulating = False):
        self.__comms = communicator()
        self._controls = controller(self.__comms)
        # self._position = self._controls.config.position
        self._min_step = {
            "x_min": self._controls._config.grid_spacing_x,
            "y_min": self._controls._config.grid_spacing_y,
            "z_min": self._controls._config.grid_spacing_z
        }
        # if not simulating:
            # self.connect()
        self.connect()
        if not simulating:
            self.update(bootup = True)
        self.set_defaults()
        # self.update()
        print("Gantry ready to go!")

    @property
    def position(self):
        return self._controls.position
    @position.setter
    def position(self, pos):
        # self._position = pos
        # self._controls.config.position = pos
        self._controls.position = pos

    @property
    def min_step(self):
        return self._min_step
    
    @min_step.setter
    def min_step(self, min_x = None, min_y = None, min_z = None):
        min_dict = {f"{ax}": ax for ax in [min_x, min_y, min_z] if ax is not None}
        self._min_step.update(min_dict)



    def connect(self):
        self._controls._comms.connect()
    def disconnect(self):
        self._controls._comms.disconnect()
    def set_defaults(self):
        self._controls.set_defaults()
    def write(self, msg):
        return self._controls._comms.write(msg)
    def _enable_steppers(self):
        self._controls._enable_steppers()
    def _disable_steppers(self):
        self._controls._disable_steppers()
    def update(self, bootup: str = False):
        self._controls.update(bootup = bootup)
    def gohome(self):
        self._controls.gohome()
    def set_speed_percentage(self, p):
        self._controls.set_speed_percentage(p = p)
    def movetoclear(self):
        self._controls.movetoclear()
    def movetoidle(self):
        self._controls.movetoidle()
    def moveto(self, x: Union[List[float], float], y = None, z = None, zhop = True, speed = None):
        self._controls.moveto(x, y, z, zhop, speed)
    def premove(self, x, y, z, zhop = True):
        return self._controls.premove(x, y, z, zhop)
    def _transition_to_frame(self, target_frame):
        self._controls._transition_to_frame(target_frame = target_frame)
    def _target_frame(self, position: Union[tuple, list]):
        return self._controls._target_frame(position)
    def _waitformovement(self):
        return self._controls._waitformovement()
    def _movecommand(self, x: float, y: float, z: float, speed: float):
        return self._controls._movecommand(x = x, y = y, z = z, speed = speed)
    def _transform_coordinates(self, x, y, z):
        return self._controls._transform_coordinates(x, y, z)
    def moverel(
        self,
        x: float = 0,
        y: float = 0,
        z: float = 0,
        zhop: bool = False,
        speed: float = None,
    ):
        self._controls.moverel(
            x = x,
            y = y,
            z = z,
            zhop = zhop,
            speed = speed
        )
    
    
    def gui(self):
        GantryGUI(gantry = self)
    # def gui(self):
    #     # app = get_qapp()

    #     gui = NewGantryGUI(self)
    #     gui.show()
    #     return gui
    # def launch_gui(self):
    #     app = get_qapp()
    #     # self._gui = NewGantryGUI(self)
    #     # self._gui = GantryControlWidget(self)
    #     self._gui = BestGantryGUI(self)
    #     self._gui.show()
    #     return self._gui
    # def open_gui(self):
    #     if not hasattr(self, "_gui") or self._gui is None:
    #         self._gui = self.launch_gui()
    #     else:
    #         self._gui.raise_()
    #         self._gui.activateWindow()

from functools import partial
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QGridLayout,
)
from PyQt5.QtCore import Qt, QCoreApplication


class NewGantryGUI(QWidget):
    WINDOW_TITLE = "PASCAL Gantry GUI"
    WINDOW_GEOMETRY = (300, 300, 600, 220)
    STEP_OPTIONS = [0.1, 1, 10, 50, 100]
    AXES = ["x", "y", "z"]

    def __init__(self, gantry):
        super().__init__()

        self.gantry = gantry
        self.stepsize = {axis: 1.0 for axis in self.AXES}
        self.position_labels = {}
        self.step_buttons = {axis: {} for axis in self.AXES}

        # self._ensure_app()
        self._build_layout()
        self._create_axes_display()
        self._create_jog_buttons()
        self._create_step_controls()
        self._create_status_label()

        self.update_position()
        self._highlight_active_steps()

        self._finalize_window()

    # -------------------------------------------------
    # App Setup
    # -------------------------------------------------

    # def _ensure_app(self):
    #     self.app = QCoreApplication.instance()
    #     if self.app is None:
    #         self.app = QApplication([])
    #     self.app.aboutToQuit.connect(self.app.deleteLater)

    # -------------------------------------------------
    # UI Construction
    # -------------------------------------------------

    def _build_layout(self):
        self.grid = QGridLayout()
        self.setLayout(self.grid)

    def _create_axes_display(self):
        for col, axis in enumerate(self.AXES):
            label = QLabel(axis.upper())
            label.setAlignment(Qt.AlignHCenter)
            self.grid.addWidget(label, 0, col)

            pos_label = QLabel("0.00")
            pos_label.setAlignment(Qt.AlignHCenter)
            self.grid.addWidget(pos_label, 1, col)

            self.position_labels[axis] = pos_label

    def _create_jog_buttons(self):
        jog_map = {
            "Forward": dict(x=0, y=1, z=0, row=2, col=1),
            "Back": dict(x=0, y=-1, z=0, row=3, col=1),
            "Left": dict(x=-1, y=0, z=0, row=3, col=0),
            "Right": dict(x=1, y=0, z=0, row=3, col=2),
            "Up": dict(x=0, y=0, z=1, row=2, col=3),
            "Down": dict(x=0, y=0, z=-1, row=3, col=3),
        }

        for name, cfg in jog_map.items():
            btn = QPushButton(name)
            btn.clicked.connect(
                partial(self.jog, x=cfg["x"], y=cfg["y"], z=cfg["z"])
            )
            self.grid.addWidget(btn, cfg["row"], cfg["col"])

    def _create_step_controls(self):
        base_row = 5

        for axis_index, axis in enumerate(self.AXES):
            for col, step in enumerate(self.STEP_OPTIONS):
                btn = QPushButton(f"{step} mm")
                btn.clicked.connect(partial(self.set_stepsize, axis, step))
                self.grid.addWidget(btn, base_row + axis_index, col)
                self.step_buttons[axis][step] = btn

    def _create_status_label(self):
        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignHCenter)
        self.grid.addWidget(self.status_label, 4, 4)

    def _finalize_window(self):
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setGeometry(*self.WINDOW_GEOMETRY)
        self.show()

        # self.app.setQuitOnLastWindowClosed(True)
        # self.app.exec_()

    # -------------------------------------------------
    # Functional Logic
    # -------------------------------------------------

    def set_stepsize(self, axis, value):
        self.stepsize[axis] = value
        self._highlight_active_steps()

    def _highlight_active_steps(self):
        for axis in self.AXES:
            for value, button in self.step_buttons[axis].items():
                if self.stepsize[axis] == value:
                    button.setStyleSheet("background-color: #a7d4d2")
                else:
                    button.setStyleSheet("")

    def jog(self, x=0, y=0, z=0):
        self._set_status("Moving", "red")

        dx = x * self.stepsize["x"]
        dy = y * self.stepsize["y"]
        dz = z * self.stepsize["z"]

        # self.gantry.moverel(dx, dy, dz)
        x, y, z = tuple(self.gantry.position)
        self.gantry.position = [x + dx, y + dy, z + dz]
        self.update_position()

        self._set_status("Idle")

    def update_position(self):
        for axis, value in zip(self.AXES, self.gantry.position):
            self.position_labels[axis].setText(f"{value:.2f}")

    def _set_status(self, text, color=None):
        self.status_label.setText(text)
        if color:
            self.status_label.setStyleSheet(f"color: {color}")
        else:
            self.status_label.setStyleSheet("")