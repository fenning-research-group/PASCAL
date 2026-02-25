from frgpascal.hardware.switchbox import Switchbox
from frgpascal.hardware.hotplate import Omega
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.spincoater import SpinCoater
from frgpascal.hardware.liquidhandler import OT2Server
import time
import threading
from threading import Lock
import asyncio
import os
import yaml
import numpy as np
from odrive.enums import *  # control/state enumerations

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["characterizationline"]

# ================
# Fakeout Switches
# ================
class FakeSwitchboxSerial:
    def __init__(self):
        self.state = {}

    def write(self, data: bytes):
        msg = data.decode().strip()

        if msg.startswith("relay on"):
            relay = msg.split()[-1]
            self.state[relay] = True
        elif msg.startswith("relay off"):
            relay = msg.split()[-1]
            self.state[relay] = False
    def readline(self):
        return b"OK\n"
    def close(self):
        pass

class FakeSwitchbox(Switchbox):
    def __init__(self, port: str = None):
        self.port = port
        self.POLLINGDELAY = constants["switchbox"][
            "pollingrate"
        ]  # delay between sending a command and reading a response, in seconds
        self.RELAYRESPONSETIME = constants["switchbox"][
            "relayresponsetime"
        ]  # delay between changing relay state and relay open/closing
        self._relay_key = {
            1: "1",
            2: "2",
            3: "3",
            4: "C",
            5: "D",
            6: "E",
            7: "F", #F originally
            8: "0",
            9: "4",
            10: "5",
            11: "6",
            12: "9",
            13: "A",
            14: "B",
            "vacuumsolenoid": "8",  # relay 8 and 9 are not being used for switchboard
            "unused": "9",
        }
        self._lock = (
            Lock()
        )
        # Fake connection:
        self.connect()
        self.fakeswitch = FakeSingleSwitch
    def connect(self):
        """
        Fake Switchbox connection
        """
        self._handle = FakeSwitchboxSerial()

class FakeSingleSwitch:
    """Exposes on/off control to a single switch"""
    def __init__(self, switchid, switchbox: FakeSwitchbox):
        self.switchid = switchid
        self.switchbox = switchbox
    def on(self):
        self.switchbox.on(self.switchid)
    def off(self):
        self.switchbox.off(self.switchid)

# ===================
# Fakeout SpinCoater:
# ===================
class FakeEncoder:
    def __init__(self):
        self.pos_estimate = 0.0
        self.vel_estimate = 0.0
class FakeController:
    def __init__(self):
        self.input_pos = 0.0
        self.input_vel = 0.0
        self.input_torque = 0.0
class FakeMotor:
    def __init__(self):
        self.current_control = type("obj", (), {"Iq_measured": 0.0})
class FakeAxis:
    def __init__(self):
        self.encoder = FakeEncoder()
        self.controller = FakeController()
        self.motor = FakeMotor()
        self.requested_state = 0
class FakeODrive:
    def __init__(self):
        self.axis0 = FakeAxis()
        self.axis1 = FakeAxis()
        self.vbus_voltage = 24.0

class FakeSpinCoater(SpinCoater):
    def __init__(self, gantry: Gantry, switch: FakeSingleSwitch, sc_axis: str = 'axis0', regular_bootup: bool = True):
        """
        Initialize the spincoater control object
        
        :param gantry: PASCAL Gantry control object
        :type gantry: Gantry
        :param switch: PASCAL FakeSingleSwitch control object
        :type switch: FakeSingleSwitch
        :param sc_axis: axis of odrive board used for this instance. Defaults to `axis0`
        :param regular_bootup: run through the bootup process. Skipping will raise errors when attempting spincoater use. Defaults to True
        :type regular_bootup: bool
        """
        self.switch = switch
        self.COMMUNICATION_INTERVAL = constants["spincoater"]["communication_interval"]
        self.TIMEOUT = 30
        self.ACCELERATIONRANGE = (
            constants["spincoater"]["acceleration_min"],
            constants["spincoater"]["acceleration_max"]
        ) # rpm / s
        self.SPEEDRANGE = (
            constants["spincoater"]["rpm_min"],
            constants["spincoater"]["rpm_max"]
        ) # rpm
        self.__rpm = 0
        self.__HOMEPOSITION = 0.5
        self.__TWISTDELTA = (
            -0.15
        )
        self._locked = False
        self.gantry = gantry
        self.__calibrated = False
        self.__logging_active = False
        self.__logdata = {"time": [], "rpm": []}
        self.LOGGINGINTERVAL = constants["spincoater"]["logging_interval"]
        self.VACUUM_DISENGAGEMENT_TIME = constants["spincoater"]["vacuum_disengagement_time"]
        self.p0 = np.asarray(constants["spincoater"]["p0"]) + [0, 0, 2]
        self.connect(sc_axis = sc_axis, regular_bootup = regular_bootup)
        self._current_rps = 0
    def fake_find_any(*args, **kwargs):
        print("Returning simulated ODrive.")
        return FakeODrive()
    def connect(self, **kwargs):
        regular_bootup = kwargs.get('regular_bootup', True)
        sc_axis = kwargs.get('sc_axis', 'axis0')
        self.odrv0 = self.fake_find_any()
        self.axis = self.odrv0.axis0
        self.lock()
        self.idle()
        self.__connected = True
        self._libfibre_watchdog = threading.Thread(
            target = self.__libfibre_timer_worker
        )
        self._libfibre_watchdog.start()
        self._error_log = []
    def disconnect(self, reboot = False):
        self.__connected = False
        self._libfibre_watchdog.join()
    def lock(self):
        if self._locked:
            return
        self._locked = True
    def idle(self):
        self._locked = False
    def stop(self):
        self.lock()
        self.idle()
    def twist_off(self):
        if not self._locked:
            self.lock()

# ===========================
# Fakeout HotPlate Controller
# ===========================

class FakeOmega(Omega):
    def __init__(self, id: int, port: str = None):
        if id not in [1, 2, 3]:
            raise ValueError("Hotplate ID must be 1 (green), 2 (pink), or 3 (blue)!")
        
        self.address = 1
        self.port = port
        self.lock = Lock()

        # Simulation
        self._sim_temperature = 25.0
        self._sim_setpoint = 0.0
        self._sim_autotune = False
        self._sim_pid_channel = 4

        self.__end = b"\r\n"
        
        # Fake connection
        self.connect()
    def connect(self):
        """
        Override the Omega().connect() to fake the serial connection
        """
        self._connected = True
        return True
    def disconnect(self):
        """
        Override the Omega().connect() to fake ending serial connection
        """
        self._connected = False
        return True
    
    def query(self, payload):
        """
        Override Omega().query() to simulate serial response 
        while preserving exact protocol format.
        
        :param payload: Output of Omega().__build_payload()
        """
        with self.lock:
            # Decode payload components
            payload_str = payload.decode()
            command = int(payload_str[3:5], 16)
            data_address = payload_str[5:9]
            if command == 3: # read the register
                if data_address == "1000": # temperature register
                    value = int(self._sim_temperature * 10)
                elif data_address == "1001": # setpoint register
                    value = int(self._sim_setpoint * 10)
                else:
                    value = 0
                response = self._build_read_response(command, data_address, value)
                return response
            elif command == 6: # write single register
                value = int(payload_str[9:13], 16)
                if data_address == "1001":
                    self._sim_setpoint = value / 10.0
                elif data_address == "101C":
                    self._sim_pid_channel = value
                return payload
            elif command == 5: #autotune controller
                self._sim_autotune = True
                return payload
            elif command == 2: # read autotune status
                status = 1 if self._sim_autotune else 0
                response = self._build_read_response(command, data_address, status)
                return response
            return payload
    def _build_read_response(self, command, data_address, value):
        """
        Build a response like Omega() expects.
        
        :param self: Description
        :param command: Description
        :param data_address: Description
        :param value: Description
        """
        # Simulate slow thermal ramp
        self._simulate_temperature_drift()
        # Build response payload same way Omega would
        content_hex = f"{value:04X}".encode()
        payload = self._Omega__numtohex(self.address)
        payload += self._Omega__numtohex(command)
        payload += data_address.encode()
        payload += content_hex
        # Recalculate checksum using parent's private method
        checksum = self._calculate_checksum(payload)
        payload += checksum
        payload += self.__end
        return b":" + payload
    def _calculate_checksum(self, payload):
        num_hex_values = int(len(payload) / 2)
        hex_values = [
            int(payload[2 * j : (2 * j) + 2], 16)
            for j in range(num_hex_values)
        ]
        checksum_int = 256 - sum(hex_values) % 256
        return f"{checksum_int:02X}".encode()
    def _simulate_temperature_drift(self):
        """
        Simulate first-order thermal response.
        """
        tau = 10.0 # seconds
        dt = 0.5
        delta = (self._sim_setpoint - self._sim_temperature) * dt / tau
        self._sim_temperature += delta

# ===================
# Fakeout OT2Server()
# ===================
class FakeOT2Server(OT2Server):
    def __init__(self, offset_time):
        self.__local_nist_offset = time.time() - offset_time
        # self._OT2Server__calibrate_time_to_nist()
        self.connected = False
        self.ip = constants["server"]["ip"]
        self.port = constants["server"]["port"]
        self.pending_tasks = []
        self.completed_tasks = {}
        self.POLLINGRATE = 1
        self.loop = asyncio.new_event_loop()
