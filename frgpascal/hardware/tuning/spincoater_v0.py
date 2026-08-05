"""A Tool for tuning the control of a BLDC motor using an ODrive V3.6 board.

This file contains methods relevant to tune the velocity and position control of the spincoater.
Main items:
- VelocityTestParams: 
    A dataclass for storing the variables chosen for a particular velocity control test.
- PositionTestParams: 
    A dataclass for storing the settings chosen for a particular position control test.
- TuneODriveLegacy:
    A class for connecting to an ODrive, testing the velocity or position control.

Example:
    from frgpascal.hardware.tuning.spincoater_v0 import *
    rpm_result, pos_result = TOD.run_tests_given_PPI(
        pos_proportional_gain = 3.0,
        vel_proportional_gain = 0.003,
        vel_integrator_gain = 0.01,
        rpm_sweep = [3000, 5000, 8000],
        pos_sweep = [0.05, 0.1, 0.15]
    )
    TOD.plot_test_performance(
        rpm_result = rpm_result,
        pos_result = pos_result
    )
"""

import time
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
from dataclasses import dataclass, fields, _MISSING_TYPE, asdict
from abc import ABC
import odrive
# from odrive.enums import (
#     AXIS_STATE_IDLE, AXIS_STATE_FULL_CALIBRATION_SEQUENCE,
# )
from odrive.utils import dump_errors

@dataclass
class BaseTestParams:
    max_test_duration: float = 60*5
    sample_rate: float = 100
    def __post_init__(self):
        for field in fields(self):
            # If there is a default and the value of the field is missing, then we can assign a value
            if not isinstance(field.default, _MISSING_TYPE) and getattr(self, field.name) is None:
                setattr(self, field.name, field.default)

@dataclass
class VelocityTestParams(BaseTestParams):
    pos_proportional_gain: float = 20 # signal -> position control node Proportional component
    vel_proportional_gain: float = 1 # position -> velocity control node Proportional control constant
    vel_integrator_gain: float = 0 # position -> velocity control node Integral control constant
    vel_accel_rate: float = 2000 # RPM/s
    vel_setpoint: float = 8000 # RPM
    spin_duration: float = 15 # s, usually we do 30-50 seconds here, but a particularly bad sample will be wobbly right away.

@dataclass
class PositionTestParams(BaseTestParams):
    pos_proportional_gain: float = 20 # signal -> position control node Proportional component
    vel_proportional_gain: float = 1 # position -> velocity control node Proportional control constant
    vel_integrator_gain: float = 0 # position -> velocity control node Integral control constant
    traptraj_vel_limit: float = 0.5
    traptraj_accel_limit: float = 0.5
    traptraj_decel_limit: float = 0.5
    traptraj_relative_move: float = 0.15
    traptraj_hold_duration: float = 5
    sample_rate: float = 100


class TuneODriveLegacy:
    def __init__(self, which_axis = "axis0"):
        self.odrv0 = self.connect()
        if "0" in which_axis:
            self.axis = self.odrv0.axis0
        else:
            self.axis = self.odrv0.axis1
        self.__show_progress = False
    def connect(self):
        print("Searching for ODrive...")
        odrv0 = odrive.find_any()
        print(f"Connected to: {odrv0.serial_number}")
        return odrv0
    
    def _calibrate(self):
        print("[START] Calibration at:", time.ctime())
        if self.axis.current_state != odrive.enums.AXIS_STATE_IDLE:
            self.axis.requested_state = odrive.enums.AXIS_STATE_IDLE
            time.sleep(1)
        self.axis.requested_state = odrive.enums.AXIS_STATE_FULL_CALIBRATION_SEQUENCE
        while self.axis.current_state != odrive.enums.AXIS_STATE_IDLE:
            time.sleep(0.1)
        self._home_pos = self.axis.encoder.pos_estimate
        if self.__show_progress:
            print(f"Calibrated home position: {self._home_pos:.4f} turns")
        print("[END] Calibration at:", time.ctime())
    
    # def _ramp_to_velocity_and_hold(self, vel_setpoint):
    #     """This one will be to test spin_steps like: [[1000, 500, 20], [8000, 1000, 30], [3684, 200, 10]]"""

    def _velocity_test(self, test_params: VelocityTestParams):
        print("[START] Velocity Ramp Test at:", time.ctime())
        self.axis.controller.config.control_mode = odrive.enums.CONTROL_MODE_VELOCITY_CONTROL
        self.axis.controller.config.input_mode = odrive.enums.INPUT_MODE_VEL_RAMP
        self.axis.controller.config.pos_gain = test_params.pos_proportional_gain
        self.axis.controller.config.vel_gain = test_params.vel_proportional_gain
        self.axis.controller.config.vel_integrator_gain = test_params.vel_integrator_gain
        vel_ramp_rate = int(test_params.vel_accel_rate / 60) # turns/sec^2
        ramp_duration = test_params.vel_setpoint / test_params.vel_accel_rate
        self.axis.controller.config.vel_ramp_rate = vel_ramp_rate
        self.axis.controller.config.vel_limit = 150 ##TODO: What are the actual units of this "vel_limit"? How high should it go to hit 8500 RPM?
        self.axis.requested_state = odrive.enums.AXIS_STATE_CLOSED_LOOP_CONTROL
        vel_data = []
        setpoint_data = []
        t_data = []
        spin_start = time.time()
        self.axis.controller.input_vel = test_params.vel_setpoint / 60
        while time.time() - spin_start < test_params.spin_duration + ramp_duration:
            vel_data.append(self.axis.encoder.vel_estimate)
            setpoint_data.append(self.axis.controller.input_vel)
            t_data.append(time.time() - spin_start)
            time.sleep(1 / test_params.sample_rate)
            if time.time() - spin_start > test_params.max_test_duration:
                raise TimeoutError("Velocity Test timeout")
        self.axis.controller.input_vel = 0
        stop_start = time.time()
        while time.time() - stop_start < 10:
            vel_data.append(self.axis.encoder.vel_estimate)
            setpoint_data.append(0)
            t_data.append(time.time() - spin_start)
            time.sleep(1 / test_params.sample_rate)
            if time.time() - stop_start > test_params.max_test_duration:
                raise TimeoutError("Velocity stop timeout")
        print("[END] Velocity Ramp Test at:", time.ctime())
        if self.axis.current_state != odrive.enums.AXIS_STATE_IDLE:
            self.axis.requested_state = odrive.enums.AXIS_STATE_IDLE
            time.sleep(1)
        velocity_result = {
            "vel_data": vel_data,
            "setpoint_data": setpoint_data,
            "time_data": t_data,
        }
        return velocity_result, test_params
    
    def _position_test(self, test_params: PositionTestParams):
        print("[START] Position TrapTraj Test", time.ctime())
        self.axis.controller.config.control_mode = odrive.enums.CONTROL_MODE_POSITION_CONTROL
        self.axis.controller.config.input_mode = odrive.enums.INPUT_MODE_TRAP_TRAJ
        if self.axis.requested_state != odrive.enums.AXIS_STATE_CLOSED_LOOP_CONTROL:
            self.axis.requested_state = odrive.enums.AXIS_STATE_CLOSED_LOOP_CONTROL
            time.sleep(1)
        self.axis.controller.config.pos_gain = test_params.pos_proportional_gain
        self.axis.controller.config.vel_gain = test_params.vel_proportional_gain
        self.axis.controller.config.vel_integrator_gain = test_params.vel_integrator_gain
        self.axis.trap_traj.config.vel_limit = test_params.traptraj_vel_limit
        self.axis.trap_traj.config.accel_limit = test_params.traptraj_accel_limit
        self.axis.trap_traj.config.decel_limit = test_params.traptraj_decel_limit
        # Clamp target position +/- 0.15 turns
        raw_target_pos = self._home_pos + test_params.traptraj_relative_move
        min_pos = self._home_pos - 0.05
        max_pos = self._home_pos + 0.05
        target_pos = max(min(raw_target_pos, max_pos), min_pos)
        pos_data = []
        pos_vel_data = []
        pos_time_data = []
        self.axis.controller.input_pos = target_pos
        test_start = time.time()
        while time.time() - test_start < test_params.traptraj_hold_duration + 3:
            pos_data.append(self.axis.encoder.pos_estimate)
            pos_vel_data.append(self.axis.encoder.vel_estimate)
            pos_time_data.append(time.time() - test_start)
            time.sleep(1 / test_params.sample_rate)
            if time.time() - test_start > test_params.max_test_duration:
                raise TimeoutError("Position test timeout")
        self.axis.controller.input_pos = self._home_pos
        time.sleep(test_params.traptraj_hold_duration)
        print("[END] Trap Traj Position Test at:", time.ctime())
        if self.axis.current_state != odrive.enums.AXIS_STATE_IDLE:
            self.axis.requested_state = odrive.enums.AXIS_STATE_IDLE
            time.sleep(1)
        position_result = {
            "pos_data": pos_data,
            "vel_data": pos_vel_data,
            "time_data": pos_time_data,
        }
        return position_result, test_params
    
    def run_tests_given_PPI(
            self,
            pos_proportional_gain,
            vel_proportional_gain,
            vel_integrator_gain,
            rpm_sweep = [3000, 5000, 6000, 8000],
            pos_sweep = [0.1, 0.15, 0.4],
        ):
        rpm_results = {}
        for rpm in tqdm(rpm_sweep):
            self._calibrate()
            self.odrv0.axis0.controller.input_vel = 0 # added axis0
            self.odrv0.axis0.requested_state = 1
            self.odrv0.clear_errors()
            if rpm not in rpm_results.keys():
                rpm_results[rpm] = {}
            veltest_params = VelocityTestParams(
                pos_proportional_gain = pos_proportional_gain,
                vel_proportional_gain = vel_proportional_gain,
                vel_integrator_gain = vel_integrator_gain,
                vel_setpoint = rpm,
            )
            vel_dict, test_params = self._velocity_test(test_params = veltest_params)
            rpm_results[rpm]['vel_dict'] = vel_dict
            rpm_results[rpm]["VelocityTestParams"] = asdict(test_params)
            
            self.odrv0.axis0.controller.input_vel = 0 # added axis0
            self.odrv0.axis0.requested_state = 1
            self.odrv0.clear_errors()
        pos_results = {}
        for pos in tqdm(pos_sweep):
            try:
                self._calibrate()
                self.odrv0.axis0.controller.input_vel = 0
                self.odrv0.axis0.requested_state = 1
                self.odrv0.clear_errors()
                if pos not in pos_results.keys():
                    pos_results[pos] = {}
                postest_params = PositionTestParams(
                    pos_proportional_gain = pos_proportional_gain,
                    vel_proportional_gain = vel_proportional_gain,
                    vel_integrator_gain = vel_integrator_gain,
                    traptraj_relative_move = pos,
                )
                pos_dict, test_params = self._position_test(test_params = postest_params)
                pos_results[pos]["pos_dict"] = pos_dict
                pos_results[pos]["PositionTestParams"] = asdict(test_params)
                
                self.odrv0.axis0.controller.input_vel = 0 # added axis0
                self.odrv0.axis0.requested_state = 1
                self.odrv0.clear_errors()
            except:
                self.odrv0.axis0.controller.input_pos = self.odrv0.encoder.pos_estimate # added axis0
                self.odrv0.axis0.requested_state = 1
                errs = self.odrv0.get_errors()
        return rpm_results, pos_results

    def plot_test_performance(self, rpm_result, pos_result):
        fig, ax = plt.subplots(2, 1)
        for idx, result in enumerate(rpm_result, pos_result):
            for k in result.keys():
                dict_key = [k_ for k_ in result[k].keys() if '_dict' in k_][0]
                times = result[k][dict_key]['time_data']
                if idx == 0:
                    process_variable = np.array(result[k][dict_key]['vel_data'])*60
                else:
                    process_variable = np.array(result[k][dict_key]['pos_data'])
                ax[idx].plot(times, process_variable, label = k)
            ax[idx].legend(bbox_to_anchor = (1.01, 1), loc = "upper left")
        ax[0].set_title("Velocity Test")
        ax[0].set_ylabel("rpm")
        ax[1].set_title("TrapTraj Position Test")
        ax[1].set_xlabel("Time (s)")
        ax[1].set_ylabel("pos (0-1)")
        plt.tight_layout()
        plt.show()
        plt.close()