import time
import re
import numpy as np
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton
import PyQt5
# from tenacity import retry
import yaml
import os
import subprocess
import serial
import socket
import select
# from PyQt5.QtCore.Qt import AlignHCenter
from functools import partial
from frgpascal.hardware.helpers import get_port


MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class Gantry:
    def __init__(self, port=None, ip=None, duet_port=None):
        # communication variables
        if port is None:
            self.port = get_port(constants["gantry"]["device_identifiers"])
            print(self.port, "if") ## added comment
        else:
            self.port = port
            print(port, "else") ## added comment
        if ip is None:
            ip = constants["gantry"]["device_identifiers"]["duet_ip"]
        if duet_port is None:
            duet_port = constants["gantry"]["device_identifiers"]["duet_port"]
        self.ip = ip
        print(self.ip)
        self.duet_port = duet_port
        self.POLLINGDELAY = constants["gantry"][
            "pollingrate"
        ]  # delay between sending a command and reading a response, in seconds
        self.inmotion = False
        self._connected_network_devices = {}
        # gantry variables
        self.__OVERALL_LIMS = constants["gantry"][
            "overall_gantry_limits"
        ]  # total coordinate system for gantry
        self.__FRAMES = {
            "workspace": constants["gantry"][
                "workspace_limits"
            ],  # accessible coordinate system for workspace
            "opentrons": constants["gantry"][
                "opentrons_limits"
            ],  # accessible coordinate system in Opentrons2 liquid handler
        }
        self.TRANSITION_COORDINATES = constants["gantry"][
            "transition_coordinates"
        ]  # point to move to when transitioning between ot2 and workspace frames
        self.CLEAR_COORDINATES = constants["gantry"]["clear_coordinates"]
        self.IDLE_COORDINATES = constants["gantry"][
            "idle_coordinates"
        ]  # where to move the gantry during idle times, mainly to avoid cameras.

        self.__currentframe = None
        self.__ZLIM = None  # ceiling for current frame

        self._original_pascal = True # False to revert to May 2025 gantry behavior.

        self.position = [
            None,
            None,
            None,
        ]  # start at None's to indicate stage has not been homed.
        self.__targetposition = [None, None, None]
        self.GANTRYTIMEOUT = constants["gantry"][
            "timeout"
        ]  # max time allotted to gantry motion before flagging an error, in seconds
        self.POSITIONTOLERANCE = constants["gantry"][
            "positiontolerance"
        ]  # tolerance for position, in mm
        self.MAXSPEED = constants["gantry"]["speed_max"]  # mm/min
        self.MINSPEED = constants["gantry"]["speed_min"]  # mm/min
        self.speed = self.MAXSPEED  # mm/min, default speed
        self.ZHOP_HEIGHT = constants["gantry"][
            "zhop_height"
        ]  # mm above endpoints to move to in between points
        self.__done_connecting = False
        self.connect()  # connect by default
        self.in_use = True
        print("gantry connected")

    # communication methods
    def connect(self, response = None):
        if response is None:
            response = input("Is the Gantry using a Duet Board? (y/n)")
            self._ethernet = response in ["y", "Y"]
        if self._ethernet:
            self.connect_ethernet()
        elif not self._ethernet:
            self.connect_usb()
        self.update()
        if self.position == [
            self.__OVERALL_LIMS["x_max"],
            self.__OVERALL_LIMS["y_max"],
            self.__OVERALL_LIMS["z_max"],
        ]:  # this is what is shows when initially turned on, but not homed
            self.position = [
                None,
                None,
                None
            ]
        self.set_defaults()
        print("Connected to Gantry")

    def connect_usb(self):
        self._handle = serial.Serial(port=self.port, timeout=1, baudrate=115200)

    def ping_duet(self, ip = "192.168.0.11", port = "23", timeout = 1000):
        """
        Ping a duet at the given ip address over a websocket connection
        """
        try:
            result = subprocess.run(
                ["ping", "-n", "5", "-w", str(timeout), ip],
                capture_output = True,
                text = True
            )
            return "Reply from" in result.stdout
        except Exception as e:
            print(f"Ping error: {e}")
            return False

    def connect_ethernet(self):
        # Have we connected to the Duet already
        if self.ip in self._connected_network_devices:
            print (self._connected_network_devices)
            print(f"Duet at {self.ip} already connected.")
            return self._connected_network_devices[self.ip]
        # Can we talk with the Duet
        # if not self.ping_duet(ip = self.ip):
            # raise ValueError(f"Duet at {self.ip}:{self.duet_port} is not reachable (ping failed)!")
        # open a TCP socket
        try:
            for port in ["23", self.duet_port, "21", "23", "80"]:
                try:
                    print(f"Trying to connect to Duet at {self.ip}:{port}...")
                    self._handle = socket.create_connection((self.ip, port), timeout = 5)
                    if port == "21":
                        print(f"\tDuet connected over OTHER type connection")
                    elif port == "23":
                        print(f"\tDuet connected over TCP type connection")
                    elif port == "80":
                        print(f"\tDuet connected over HTTP type connection")
                    self.duet_port = port
                    break
                except Exception as e:
                    print(f"\tConnecting at {self.ip}:{port} failed\n\t{e}")
            self._connected_network_devices[self.ip] = self._handle
            print(f"Connected to Duet at {self.ip}:{port}")
        except Exception as e:
            raise ValueError(f"Failed to connect to Duet at {self.ip}:{port}! \n{e}")
    
    # def send_gcode(self, command, homing = False):
    #     """
    #     Send a G-code command to the Duet over the given socket.
    #     Return the response string.
    #     """
    #     if not self._handle:
    #         raise ValueError("Socket is not connected, be sure to run Gantry().connect() first!")
    #     self._handle.sendall((command + "\n").encode("utf-8"))
    #     if homing:
    #         self._handle.settimeout(None)
    #         response = self._handle.recv(1024).decode("utf-8").strip()
    #         self._handle.settimeout(30)
    #     else:
    #         reponse = self._handle.recv(1024).decode("utf-8").strip()
    #     return response

    def send_gcode(self, command, homing = False):
        """
        Send a G-code command to the Duet over the given socket.
        Return the response string.
        """
        if not self._handle:
            raise ValueError("Socket is not connected, be sure to run Gantry().connect() first!")
        # print("im still running")
        self._handle.sendall((command + "\n").encode("utf-8"))
        if not self.__done_connecting:
            homing = False
        if homing:
            self._handle.settimeout(None)
            response_0 = self._handle.recv(1024).decode("utf-8")
            response = response_0.split()
            self._handle.settimeout(30)
        else:
            response = self._handle.recv(1024).decode("utf-8").strip()
            response_0 = None
        return response_0, response

    def disconnect(self):
        self._handle.close()
        del self._handle

    def set_defaults(self):
        if self._ethernet:
            self.write("M501")
            self.write("G90")
            # self.write(
                # f"M203 X{self.MAXSPEED} Y{self.MAXSPEED} Z{30}"
            # )
        else:
            self.write("M501")  # load defaults from EEPROM
            self.write("G90")  # absolute coordinate system
            # self.write(
            #     "M92 X26.667 Y26.667 Z200.0"
            # )  # set steps/mm, randomly resets to defaults sometimes idk why
            # self.write(
            #     "M92 X53.333 Y53.333 Z200.0"
            # )  # set steps/mm, randomly resets to defaults sometimes idk why
            # self.write(
            #     "M92 X79.5" # set steps/mm if using 2mm pitch belts on x-axis
            # )
            self.write(
                "M92 X53" # set steps/mm if using 3mm pitch belts on x-axis
            )
            self.write(
                "M906 X800 Y800 Z800 E1"
            )  # set max stepper RMS currents (mA) per axis. E = extruder, unused to set low
            self.write(
                "M84 S0"
            )  # disable stepper timeout, steppers remain engaged all the time
            self.write(
                f"M203 X{self.MAXSPEED} Y{self.MAXSPEED} Z20.00"
            )  # set max speeds, steps/mm. Z is hardcoded, limited by lead screw hardware.
        self.set_speed_percentage(80)  # set speed to 80% of max

    def write(self, msg):
        # print("cool thing: {self._ethernet})")
        if self._ethernet:
            output = [self.send_gcode(msg, homing = True)]
        else:
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
        print("UPDATING:")
        found_coordinates = False
        while not found_coordinates:
            output = self.write("M114")  # get current position
            print("\t", output)
            print("\t", type(output))
            print("\t", len(output))
            output, output2 = output[0]
            if output is None:
                output = output2
            if isinstance(output, str):
                output = [output]
            for line in output:
                print(line)
                if line.startswith("X:"):
                    x = float(re.findall(r"X:(\S*)", line)[0])
                    y = float(re.findall(r"Y:(\S*)", line)[0])
                    z = float(re.findall(r"Z:(\S*)", line)[0])
                    found_coordinates = True
                    # print(f'Home is @ [{x}, {y}, {z}]')
                    break
        self.position = [
            round(x, 1), round(y,1), round(z,1)]
        self.__currentframe = self._target_frame(*self.position)
        print(f"\t\t{self.__currentframe}")
        if self._original_pascal:
            self.__ZLIM = self.__FRAMES[self.__currentframe]["z_max"]
        else:
            self.__ZLIM = (
                self.__FRAMES["opentrons"]["z_max"] - 3
            )  # never really needs to go above the height of the opentrons height limit, -3 for buffer
        # self.__ZLIM = (
        #         self.__FRAMES["opentrons"]["z_max"] - 3
        #     )  
        # if self.servoangle > self.MINANGLE:
        self.__gripper_last_opened = time.time()

    # gantry methods
    def set_speed_percentage(self, p):
        if p < 0 or p > 100:
            raise Exception("Speed must be set by a percentage value between 0-100!")
        self.speed = (p / 100) * (self.MAXSPEED - self.MINSPEED) + self.MINSPEED

        self.write(f"G0 F{self.speed}")

    def gohome(self):
        # self.movetoclear()
        self.write("G28 X Y Z")
        self.update()
        self.movetoclear()

    def _target_frame(self, x, y, z):
        """Checks whether a target coordinate is within the liquid handler (OT2), workspace (over the breadboard), or invalid coordinate frames

        Args:
            x (float): x coordinate
            y (float): y coordinate
            z (float): z coordinate

        Returns:
            string: name of frame. if none, returns 'invalid'
        """
        for frame, lims in self.__FRAMES.items():
            print(f"\tchecking frame {frame}")
            if x < lims["x_min"] or x > lims["x_max"]:
                print(f"\t\t{x} is outside bounds")
                continue
            if y < lims["y_min"] or y > lims["y_max"]:
                print(f"\t\t{y} is outside bounds")
                continue
            if z < lims["z_min"] or z > lims["z_max"]:
                print(f"\t\t{z} is outside bounds")
                continue
            print(f"\tthe position [{x}, {y}, {z}] is inside of frame {frame}")
            return frame
        return "invalid"

    def _transition_to_frame(self, target_frame):
        if self._original_pascal:
            self._movecommand(
                self.position[0],
                y = self.position[1],
                z = self.TRANSITION_COORDINATES[2] - 1, #to be within bounds of opentrons
                speed = self.speed,
            ) # move in just z
            # nudge the gantry into the target frame
            x, y, z = self.TRANSITION_COORDINATES
            if target_frame == "opentrons":
                x -= 0.2
                self.__ZLIM = constants["gantry"]["opentrons_limits"]["z_max"]
            else:
                x += 0.2
                self.__ZLIM = constants["gantry"]["workspace_limits"]["z_max"]
            self._movecommand(x, y, z, speed = self.speed)
            print(f'\tGantry is now at Transition Coordinates: \n\t[{x}, {y}, {z}]')
        else:
            self._movecommand(
                x=self.position[0],
                y=self.position[1],
                z=self.__ZLIM,
                speed=self.speed,
            )  # move just in z

            # nudge the gantry into the target frame
            x, y, z = self.TRANSITION_COORDINATES
            z = self.__ZLIM
            if target_frame == "opentrons":
                x -= 0.2
            else:
                x += 0.2
            self._movecommand(x, y, z, speed=self.speed)

    def _move_below_opentrons_limits(self, x, y, z):
        self._movecommand(x, y, z, speed=self.speed)

    def premove(self, x, y, z, zhop=True):
        """
        checks to confirm that all target positions are valid
        """
        if self.position == [None, None, None]:
            raise Exception(
                "Stage has not been homed! Home with self.gohome() before moving please."
            )
        if x is None:
            x = self.position[0]
        if y is None:
            y = self.position[1]
        if z is None:
            z = self.position[2]
        print(f"Checking x: {x}, y: {y}, z: {z}")
        # print(f"type of the y object: {type(y)}")
        # if isinstance(y, float):
            # y = round(y, 1)

        # check if we are transitioning between workspace/gantry, if so, handle it
        target_frame = self._target_frame(x, y, z)
        print(target_frame)
        cur_frames = list(self.__FRAMES.keys())
        if target_frame not in cur_frames:
            print(f"frame {target_frame} is not in the defined frames!")
        if target_frame == "invalid":
            raise ValueError(f"Coordinate ({x}, {y}, {z}) is invalid!")
        if self._original_pascal:
            if self.__currentframe != target_frame:
                print(f"\ttime to transition to a new frame")
                self._transition_to_frame(target_frame)
            return x, y, z
        else:
            # checks to see if current z is more than 5mm below opentrons limits
            # and same for y
            opentrons_z_max_limit = constants["gantry"]["opentrons_limits"]["z_max"] - 3
            opentrons_y_min_limit = 60
            transition_coord = constants["gantry"]["transition_coordinates"]
            if self.__currentframe != target_frame:
                # if z > opentrons_z_max_limit:
                #     z = opentrons_z_max_limit
                # if y < opentrons_y_min_limit:
                #     y = opentrons_y_min_limit
                if zhop:
                    self._movecommand(
                        self.position[0],
                        self.position[1],
                        self.__ZLIM,
                        speed=self.speed,
                        m400=True,
                    )
                    print("zhopping")
                self._movecommand(
                    transition_coord[0],
                    transition_coord[1],
                    transition_coord[2],
                    speed=self.speed,
                    m400=True,
                )

            # elif self.__currentframe != target_frame and zhop:
            #     print("This motion wants to zhop while doing a frame transition!")

            return x, y, z

    def moveto(self, x=None, y=None, z=None, zhop=True, speed=None, m400=False):
        """
        moves to target position in x,y,z (mm)
        """
        try:
            if len(x) == 3:
                x, y, z = x  # split 3 coordinates into appropriate variables
        except:
            pass
        if self._original_pascal:
            # x = np.round(x, decimals = 1)
            # y = np.round(y, decimals = 1)
            # z = np.round(z, decimals = 1)
            print(x, y, z)
            x, y, z = self._transform_coordinates(x, y, z)
            x, y, z = self.premove(x, y, z) # will error out if invalid move
            if speed is None:
                speed = self.speed
            if (x == self.position[0]) and (y == self.position[1]):
                zhop = False # no use zhopping for no lateral movement
            if zhop:
                
                z_ceiling = max(self.position[2], z) + self.ZHOP_HEIGHT
                print(f"\tz_ceil: {z_ceiling}, ZLIM: {self.__ZLIM}")
                z_ceiling = min(
                    z_ceiling, self.__ZLIM
                ) # cant z-hop above build volume. mostly here for first move after homing
                print(f"\tmoving to z_ceil: {z_ceiling}")
                self.moveto(z = z_ceiling, zhop = False, speed = speed)
                print(f"\tmoving to x, y: {x}, {y}")
                self.moveto(x, y, z_ceiling, zhop = False, speed = speed)
                print(f"\tmoving to z: {z}")
                self.moveto(z=z, zhop = False, speed = speed)
            else:
                self._movecommand(x, y, z, speed)
        else:
            x, y, z = self.premove(x, y, z, zhop)  # will error out if invalid move
            # print(f"\tGantry moving to:\n\t\tx: {x}, y: {y}, z: {z}")
            if speed is None:
                speed = self.speed
            if (x == self.position[0]) and (y == self.position[1]):
                zhop = False  # no use zhopping for no lateral movement

            # if self.position[2] > self.__ZLIM:
            #     m400 = True

            if zhop:
                z_ceiling = max(self.position[2], z) + self.ZHOP_HEIGHT
                z_ceiling = min(
                    z_ceiling, self.__ZLIM
                )  # cant z-hop above build volume. mostly here for first move after homing.
                if self._original_pascal:
                    self.moveto(z=z_ceiling, zhop = False, speed = speed)
                    self.moveto(x, y, z_ceiling, zhop=False, speed=speed)
                    self.moveto(z=z, zhop=False, speed=speed)
                else:
                    self.moveto(z=self.__ZLIM, zhop=False, speed=speed, m400=True)
                    self.moveto(x, y, self.__ZLIM, zhop=False, speed=speed, m400=True)
                    self.moveto(z=z, zhop=False, speed=speed, m400=True)

            else:
                self._movecommand(x, y, z, speed, m400)

    def movetoclear(self):
        self.moveto(self.CLEAR_COORDINATES)

    def movetoidle(self):
        self.moveto(self.IDLE_COORDINATES)

    def _movecommand(self, x: float, y: float, z: float, speed: float, m400=False):
        """internal command to execute a direct move from current location to new location"""
        if self.position == [x, y, z]:
            return True  # already at target position
        else:
            x = np.round(x, decimals = 1)
            y = np.round(y, decimals = 1)
            z = np.round(z, decimals = 1)
            self.__targetposition = [x, y, z]
            self.write(f"G0 X{x} Y{y} Z{z} F{speed}")
            if self._original_pascal:
                return self._waitformovement()
            else:
                return self._waitformovement(m400)

    def moverel(self, x=0, y=0, z=0, zhop=False, speed=None):
        """
        moves by coordinates relative to the current position
        """
        try:
            if len(x) == 3:
                x, y, z = x  # split 3 coordinates into appropriate variables
        except:
            pass
        x += self.position[0]
        y += self.position[1]
        z += self.position[2]
        self.moveto(x, y, z, zhop, speed)

    def _ready_to_talk(self):
        if self._ethernet:
            return True
        else:
            return self._handle.in_waiting

    def _waitformovement(self, m400 = False):
        """
        Confirm that gantry has reached target position. returns False if 
        target position is not reached in time alloted by self.GANTRYTIMEOUT
        
        :param m400: bool, whether to wait for all current moves to finish 
            before moving on.
        """
        self.inmotion = True
        start_time = time.time()
        time_elapsed = time.time() - start_time
        if self._original_pascal:
            self.write("M400")
        else:
            if m400 is True:
                self.write("M400")
        
        if self._ethernet:
            echo_command = 'M118 S"FinishedMoving"'
            self._handle.sendall((echo_command + "\n").encode("utf-8"))
        else:
            echo_command = "M118 E1 FinishedMoving"
            self._handle.write(echo_command)
        
        reached_destination = False
        while not reached_destination and time_elapsed < self.GANTRYTIMEOUT:
            print("Are we there yet?")
            time.sleep(self.POLLINGDELAY)
            yapping = self._ready_to_talk()
            while yapping:
                print("Ready to talk")
                if self._ethernet:
                    self._handle.settimeout(None)
                    line = self._handle.recv(1024).decode("utf-8").strip()
                    # print(line)
                else:
                    line = self._handle.readline().decode("utf-8").strip()
                done_move = "FinishedMoving" in line
                yapping = self._ready_to_talk()
                print(f"done_move: {done_move}")
                if done_move:
                    print(f"\tUpdating...")
                    self.update()
                    print(f"\tUpdated!")
                    print(f"self.position: {self.position}")
                    print(f"self.__targetposition: {self.__targetposition}")
                    print(0 == int(np.linalg.norm([a - b for a, b in zip(self.position, self.__targetposition)])))
                    print(0 == np.linalg.norm([a - b for a, b in zip(self.position, self.__targetposition)]))
                    if (
                        np.linalg.norm(
                            [
                                a - b
                                for a, b in zip(
                                    self.position,
                                    self.__targetposition
                                )
                            ]
                        ) == 0
                    ):
                        reached_destination = True
                        # yapping = False
                        break
                time.sleep(self.POLLINGDELAY)
        self.inmotion = ~reached_destination
        self.update()

        return reached_destination
    
    def _transform_coordinates(self, x: float, y: float, z: float):
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
        self.grid_spacing_x = 0.072
        self.grid_spacing_y = 0.075
        self.grid_spacing_z = 0.075
        if x is not None:
            x = int(round(x / self.grid_spacing_x)) * self.grid_spacing_x
        if y is not None:
            y = int(round(y / self.grid_spacing_y)) * self.grid_spacing_y
        if z is not None:
            z = int(round(z / self.grid_spacing_z)) * self.grid_spacing_z
        return x, y, z
    
    # GUI
    def gui(self):
        GantryGUI(gantry=self)  # opens blocking gui to manually jog motors


class GantryGUI:
    def __init__(self, gantry):
        AlignHCenter = PyQt5.QtCore.Qt.AlignHCenter
        self.gantry = gantry
        self.app = PyQt5.QtCore.QCoreApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        # self.app = QApplication(sys.argv)
        self.app.aboutToQuit.connect(self.app.deleteLater)
        self.win = QWidget()
        self.grid = QGridLayout()
        self.stepsize = 1  # default step size, in mm

        ### axes labels
        for j, label in enumerate(["X", "Y", "Z"]):
            temp = QLabel(label)
            temp.setAlignment(AlignHCenter)
            self.grid.addWidget(temp, 0, j)

        ### position readback values
        self.xposition = QLabel("0")
        self.xposition.setAlignment(AlignHCenter)
        self.grid.addWidget(self.xposition, 1, 0)

        self.yposition = QLabel("0")
        self.yposition.setAlignment(AlignHCenter)
        self.grid.addWidget(self.yposition, 1, 1)

        self.zposition = QLabel("0")
        self.zposition.setAlignment(AlignHCenter)
        self.grid.addWidget(self.zposition, 1, 2)

        self.update_position()

        ### status label
        self.gantrystatus = QLabel("Idle")
        self.gantrystatus.setAlignment(AlignHCenter)
        self.grid.addWidget(self.gantrystatus, 5, 4)

        ### jog motor buttons
        self.jogback = QPushButton("Back")
        self.jogback.clicked.connect(partial(self.jog, y=-1))
        self.grid.addWidget(self.jogback, 3, 1)

        self.jogforward = QPushButton("Forward")
        self.jogforward.clicked.connect(partial(self.jog, y=1))
        self.grid.addWidget(self.jogforward, 2, 1)

        self.jogleft = QPushButton("Left")
        self.jogleft.clicked.connect(partial(self.jog, x=-1))
        self.grid.addWidget(self.jogleft, 3, 0)

        self.jogright = QPushButton("Right")
        self.jogright.clicked.connect(partial(self.jog, x=1))
        self.grid.addWidget(self.jogright, 3, 2)

        self.jogup = QPushButton("Up")
        self.grid.addWidget(self.jogup, 2, 3)
        self.jogup.clicked.connect(partial(self.jog, z=1))

        self.jogdown = QPushButton("Down")
        self.jogdown.clicked.connect(partial(self.jog, z=-1))
        self.grid.addWidget(self.jogdown, 3, 3)

        ### step size selector buttons
        self.steppt1 = QPushButton("0.1 mm")
        self.steppt1.clicked.connect(partial(self.set_stepsize, stepsize=0.1))
        self.grid.addWidget(self.steppt1, 5, 0)
        self.step1 = QPushButton("1 mm")
        self.step1.clicked.connect(partial(self.set_stepsize, stepsize=1))
        self.grid.addWidget(self.step1, 5, 1)
        self.step10 = QPushButton("10 mm")
        self.step10.clicked.connect(partial(self.set_stepsize, stepsize=10))
        self.grid.addWidget(self.step10, 5, 2)
        self.step50 = QPushButton("50 mm")
        self.step50.clicked.connect(partial(self.set_stepsize, stepsize=50))
        self.grid.addWidget(self.step50, 6, 0)
        self.step100 = QPushButton("100 mm")
        self.step100.clicked.connect(partial(self.set_stepsize, stepsize=100))
        self.grid.addWidget(self.step100, 6, 1)

        self.stepsize_options = {
            0.1: self.steppt1,
            1: self.step1,
            10: self.step10,
            50: self.step50,
            100: self.step100,
        }

        self.set_stepsize(self.stepsize)

        self.run()

    def set_stepsize(self, stepsize):
        self.stepsize = stepsize
        for setting, button in self.stepsize_options.items():
            if setting == stepsize:
                button.setStyleSheet("background-color: #a7d4d2")
            else:
                button.setStyleSheet("background-color: None")

    def jog(self, x=0, y=0, z=0):
        self.gantrystatus.setText("Moving")
        self.gantrystatus.setStyleSheet("color: red")
        self.gantry.moverel(x * self.stepsize, y * self.stepsize, z * self.stepsize)
        self.update_position()
        self.gantrystatus.setText("Idle")
        self.gantrystatus.setStyleSheet("color: None")

    def update_position(self):
        for position, var in zip(
            self.gantry.position, [self.xposition, self.yposition, self.zposition]
        ):
            var.setText(f"{position:.2f}")

    def run(self):
        self.win.setLayout(self.grid)
        self.win.setWindowTitle("PASCAL Gantry GUI")
        self.win.setGeometry(300, 300, 500, 150)
        self.win.show()
        self.app.setQuitOnLastWindowClosed(True)
        self.app.exec_()
        # self.app.quit()
        # sys.exit(self.app.exec_())
        # self.app.exit()
        # sys.exit(self.app.quit())
        return
