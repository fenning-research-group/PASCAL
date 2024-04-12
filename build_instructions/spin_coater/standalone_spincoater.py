import time 
import odrive
from odrive.enums import *
import numpy as np
from datetime import datetime
import os
import serial
import yaml
from frgpascal.hardware.switchbox import Switchbox
from frgpascal.hardware.switchbox import SingleSwitch
from frgpascal.hardware.helpers import get_port


MODULE_DIR = os.path.dirname(__file__)
CALIBRATION_DIR = os.path.join(MODULE_DIR, "calibrations")

with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.Loader)


        # self.switchbox = Switchbox()

class SpinCoater:
    def __init__(self):
        self.sb = Switchbox()
        self.switch = SingleSwitch(switchid="vacuumsolenoid", switchbox=self.sb)
        #, switch: SingleSwitch):
        """Initialize the spincoater control object

        Args:
        gantry (Gantry): PASCAL Gantry control object
        serial_number (str, optional): Serial number for spincoater arduino, used to find and connect to correct COM port. Defaults to "558383339323513140D1":str.
        p0 (tuple, optional): Initial guess for gantry coordinates to drop sample on spincoater. Defaults to (52, 126, 36):tuple.
        """
        # COM4: Numato Lab 16 Channel USB Relay Module (COM4) [USB VID:PID=2A19:0C03 SER=NLRL240501R0145 LOCATION=1-1]
        # constants
        # self.switch = 
        # if port is None:
        #     self.port = get_port(
        #         constants["spincoater"]["device_identifiers"]
        #     )  # find port to connect to this device.
        # else:
        #     self.port = port
        # self.ARDUINOTIMEOUT = constants["spincoater"]["pollingrate"]
        ## self.switch = switch
        # self.port = 

        print('FRG Custom Spin Coater\nPlease Cite Our Paper!')
        self.COMMUNICATION_INTERVAL = 0.1
        self.TIMEOUT = 30

        self.ACCELERATIONRANGE = (
            50,
            5000,
        )  # rpm/s
        self.SPEEDRANGE = (
            200,
            9000,
        )  # rpm
        self.__rpm = 0  # nominal current rpm. does not take ramping into account
        self.__HOMEPOSITION = 0.5  # home coordinate for spincoater chuck, in radial (0-1) coordinates. somewhat arbitrary, but avoid 0 because it wraps around to 1, makes some math annoying
        self._locked = False  # true when chuck is holding at home position

        self.__calibrated = False
        
        # logging
        # self.__logging_active = False
        # self.__logdata = {"time": [], "rpm": []}
        # self.LOGGINGINTERVAL = constants["spincoater"]["logging_interval"]

        # self.VACUUM_DISENGAGEMENT_TIME = constants["spincoater"][
        #     "vacuum_disengagement_time"
        # ]

        self.connect()
        self._current_rps = 0

    def connect(self, **kwargs):
        # connect to odrive BLDC controller

        print("Connecting to odrive")
        # this is admittedly hacky. Connect, reboot (which disonnects), then connect again. Reboot necessary when communication line is broken
        self.odrv0 = odrive.find_any()
        # try:
        #     self.odrv0 = odrive.find_any(timeout=3)
        # except:
        #     raise ValueError("Could not find odrive! confirm that 24V PSU is on")
        # try:
        #     self.odrv0.reboot()  # reboot the odrive, communication sometimes gets broken when we disconnect/reconnect
        #     self.odrv0._destroy()
        # except:
        #     pass  # this always throws an "object lost" error...which is what we want
        # try:
        #     self.odrv0 = odrive.find_any(timeout=3)
        # except:
        #     raise ValueError("Could not find odrive! confirm that 24V PSU is on")

        print("\tFound motor, now calibrating. This takes 10-20 seconds.")
        # input("\tPress enter once shroud is out of the way: ")
        self.sc = self.odrv0.axis0
        self.sc.requested_state = (
            AXIS_STATE_FULL_CALIBRATION_SEQUENCE  # calibrate the encoder
        )
        time.sleep(5)  # wait for calibration to initiate

        while self.sc.current_state != 1:
            time.sleep(1)  # wait for calibration to complete

        self.sc.requested_state = (
            AXIS_STATE_ENCODER_OFFSET_CALIBRATION  # calibrate the encoder
        )
        time.sleep(5)  # wait for calibration to initiate
        while self.sc.current_state != 1:
            time.sleep(1)  # wait for calibration to complete
        print("\tDone calibrating odrive!")
        
        # Ensure PID Control is set up: https://docs.odriverobotics.com/v/0.5.5/control.html
        self.sc.controller.config.pos_gain = 5
        time.sleep(.1)
        self.sc.controller.config.vel_gain = 0.005
        time.sleep(.1)
        self.sc.controller.config.vel_integrator_gain = 0.5 * 10 * 0.005 #vel_integrator_gain = 0.5 * 10 * <vel_gain>
        time.sleep(.1)

        self.sc.requested_state = (
            AXIS_STATE_CLOSED_LOOP_CONTROL  # normal control mode
        )
        # odrive defaults
        # self.sc.motor.config.current_lim = 10  # Amps NOT SAME AS POWER SUPPLY CURRENT. This is targeting ~25% of the specified max motor current
        self.sc.controller.config.circular_setpoints = True  # position = 0-1 radial
        self.sc.trap_traj.config.vel_limit = (
            0.5  # for position moves to lock position
        )
        self.sc.trap_traj.config.accel_limit = 0.5
        self.sc.trap_traj.config.decel_limit = 0.5
        # self.lock()
        # time.sleep(1)
        # self.idle()


    def idle(self):
        if self.sc.current_state != AXIS_STATE_IDLE:
            self.sc.requested_state = AXIS_STATE_IDLE
        self._locked = False

    def set_rpm(self, rpm: int, acceleration: float = 1000):
    
        if rpm != 0 and (rpm < self.SPEEDRANGE[0] or rpm > self.SPEEDRANGE[1]):
            raise ValueError(
                f"RPM out of range. Must be between {self.SPEEDRANGE[0]} and {self.SPEEDRANGE[1]}"
            )
        if (
            acceleration < self.ACCELERATIONRANGE[0]
            or acceleration > self.ACCELERATIONRANGE[1]
        ):
            raise ValueError(
                f"Acceleration out of range. Must be between {self.ACCELERATIONRANGE[0]} and {self.ACCELERATIONRANGE[1]}"
            )
        
        if acceleration == 0:
            acceleration = self.ACCELERATIONRANGE[1]  # default to max acceleration

        self.sc.controller.config.circular_setpoints = True   
        time.sleep(.1)
        self.sc.trap_traj.config.accel_limit = 0.5
        time.sleep(.1)
        self.sc.trap_traj.config.decel_limit = 0.5
        rps = int(rpm / 60)  # convert rpm to rps for odrive
        acceleration = int(acceleration / 60)  # convert rpm/s to rps/s for odrive
        self.sc.controller.config.vel_ramp_rate = acceleration
        time.sleep(.1)
        self.sc.controller.input_vel = rps
        time.sleep(.1)
        self.sc.controller.config.control_mode = CONTROL_MODE_VELOCITY_CONTROL
        time.sleep(.1)
        self.sc.controller.config.input_mode = INPUT_MODE_VEL_RAMP
        if self.sc.current_state != AXIS_STATE_CLOSED_LOOP_CONTROL:
            self.sc.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL

        self._current_rps = rps
        self._locked = False


    def lock(self, lock_position=0.5):
        """
        routine to lock rotor in registered position for sample transfer
        """
        if self._locked:
            return
        if self.sc.current_state != AXIS_STATE_CLOSED_LOOP_CONTROL:
            self.sc.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
        self.sc.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ
        # self.axis.controller.config.input_mode = INPUT_MODE_POS_FILTER
        self.sc.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
        time.sleep(.1)
        self.sc.controller.input_pos = lock_position

        t0 = time.time()
        while (
            np.abs(lock_position - self.sc.encoder.pos_circular) > 0.025
        ):  # tolerance = 360*value degrees, 0.025 ~= 10 degrees
            time.sleep(0.1)
            if time.time() - t0 > 10:
                print("resetting")
                self.reset()
                t0 = time.time()
        self._locked = True
        time.sleep(.1)
        self.idle()


    def stop(self):
        """
        stop rotation and locks the rotor in position
        """
        if self._locked:
            return
        self.set_rpm(0, 1000)
        t0 = time.time()
        min_stopped_time = 2
        while True:
            if self.sc.encoder.vel_estimate > 0:
                t0 = time.time()
            if time.time() - t0 > min_stopped_time:
                break
            time.sleep(0.1)
        self.lock()
        self.idle()

    def reset(self):
        try:
            self.disconnect()
        except:
            pass
        self.connect()


    def vacuum_on(self):
        """Turn on vacuum solenoid, pull vacuum"""
        self.switch.on()

    def vacuum_off(self):
        """Turn off vacuum solenoid, do not pull vacuum"""
        self.switch.off()


    def disconnect(self):
        self.__connected = False
        # self._libfibre_watchdog.join()
        try:
            self.odrv0._destroy()
        except:
            pass  # this always throws an "object lost" error...which is what we want
    def __del__(self):
        self.disconnect()