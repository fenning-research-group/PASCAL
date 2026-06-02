import argparse
import time
import asyncio
import ntplib
import numbers
from warnings import warn

# Adjust these imports to match your actual file structure
from frgpascal.hardware.spincoater import SpinCoater
from frgpascal.hardware.switchbox import Switchbox
from frgpascal.workers import Worker_SpincoaterLiquidHandler
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper
from frgpascal.hardware.liquidhandler import OT2
from frgpascal.hardware.hotplate import HotPlate
from frgpascal.hardware.sampletray import SampleTray

# Assuming you have the liquid handler class somewhere
# from frgpascal.hardware.liquidhandler import LiquidHandler 
import os
import yaml

MODULE_DIR = os.path.dirname(__file__)
print(MODULE_DIR)
os.chdir(MODULE_DIR)
idx = 1
while 'frgpascal' != os.path.basename(MODULE_DIR) and idx < 5:
    os.chdir("..")
    MODULE_DIR = os.getcwd()
    print(MODULE_DIR)
    idx +=1
print(MODULE_DIR)
with open(os.path.join(MODULE_DIR, "hardware", "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class DummySwitch:
    """Mock switch to prevent vacuum errors if not testing the vacuum"""
    def on(self): pass
    def off(self): pass

class DummyGantry:
    """Mock gantry to satisfy SpinCoater __init__ without moving the arm"""
    def __init__(self):
        self.position = [0, 0, 0]
        self.in_use = False
    def moveto(self, x):
        pass
    def gui(): pass

class DummyGripper:
    """Mock gantry to satisfy SpinCoater __init__ without moving the arm"""
    def __init__(self):
        self.position = [0, 0, 0]
        self.in_use = False
    def moveto(self, x):
        pass
    def gui(): pass


class DummyMaestro:
    """A lightweight mock clock to bypass the full PASCAL planner"""
    def __init__(self, spincoater, liquidhandler):
        self.spincoater = spincoater
        self.liquidhandler = liquidhandler
        self.__calibrate_time_to_nist()
        print(self.nist_time)
    
    ### Time Synchronization with NIST
    def __calibrate_time_to_nist(self):
        client = ntplib.NTPClient()
        response = None
        t0 = time.time()
        while response is None:
            try:
                response = client.request("europe.pool.ntp.org", version=3)
            except:
                pass
            if time.time() - t0 >= 10:
                warn("Could not get NIST time!")
                return
        self.__local_nist_offset = response.tx_time - time.time()

    @property
    def nist_time(self):
        # The worker heavily relies on this property to sync drops perfectly
        return time.time() + self.__local_nist_offset
    
    def make_background_event_loop(self):
        def exception_handler(loop, context):
            print("Exception raised in Maestro loop")
            # self.logger.error(json.dumps(context))
            pass

        self.loop = asyncio.new_event_loop()
        self.loop.set_exception_handler(exception_handler)
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._keep_loop_running())
    
    async def _keep_loop_running(self):
        experiment_started = False
        experiment_completed = False
        done_spinning = False
        while self.working:
            if (not done_spinning):
                # done_spinning = self.singlespin.DONE_SPINNING
                await asyncio.sleep(5)

# def main():
#     # 1. Define the Terminal Commands
#     parser = argparse.ArgumentParser(description="PASCAL Single Spin & Drop CLI")
#     parser.add_argument("--rpm", type=int, required=True, help="Spin speed in RPM")
#     parser.add_argument("--duration", type=int, required=True, help="Spin duration in seconds")
#     parser.add_argument("--accel", type=float, default=1000.0, help="Acceleration in RPM/s (default: 1000)")
#     parser.add_argument("--vol", type=float, required=True, help="Antisolvent volume in uL")
#     parser.add_argument("--drop_time", type=float, required=True, help="Seconds into the spin to drop antisolvent")
    
#     args = parser.parse_args()

#     # 2. Initialize Hardware Directly
#     print("Connecting to SpinCoater (ODrive)...")
#     try:
#         # We pass the dummy gantry and switch to isolate the spincoater testing
#         dummy_gantry = DummyGantry()
#         dummy_switch = DummySwitch()
        
#         # Initialize. Note: regular_bootup=True will trigger the ODrive calibration sequence
#         spincoater = SpinCoater(gantry=dummy_gantry, switch=dummy_switch, regular_bootup=True)
#     except Exception as e:
#         print(f"Failed to connect to SpinCoater: {e}")
#         return

#     print("Connecting to Liquid Handler...")
#     # liquidhandler = LiquidHandler() # Uncomment and adjust based on actual initialization
#     liquidhandler = None # Placeholder until Opentrons is imported

#     # 3. Create Dummy Maestro and Worker
#     maestro = DummyMaestro(spincoater, liquidhandler)
#     worker = Worker_SpincoaterLiquidHandler(maestro=maestro, planning=False)

#     # 4. Construct the "Details" Dictionary matching workers.py expectations
#     details = {
#         "steps": [
#             {
#                 "rpm": args.rpm,
#                 "acceleration": args.accel, 
#                 "duration": args.duration
#             }
#         ],
#         "drops": [
#             {
#                 "time": args.drop_time,
#                 "volume": args.vol,
#                 "rate": 100, # Default dispensing rate
#                 "height": 2, # Default drop height
#                 "slow_travel": False,
#                 "slow_retract": False,
#                 "air_gap": False,
#                 "touch_tip": False,
#                 "pre_mix": [0, 0],
#                 "reuse_tip": False,
#                 "solution": {"well": {"labware": "target_tray_name", "well": "A1"}} # **Requires real labware keys**
#             }
#         ]
#     }

#     # 5. Execute using asyncio
#     print(f"\nExecuting {args.rpm} RPM for {args.duration}s with {args.vol}uL drop at {args.drop_time}s.")
#     try:
#         loop = asyncio.get_event_loop()
#         # Pass a mock sample dictionary
#         result = loop.run_until_complete(worker.spincoat(sample={"name": "Single_Drop_Test"}, details=details))
#         print("\nProcess Complete! Log Data:")
#         print(result)
#     except Exception as e:
#         print(f"\nError during execution: {e}")
#     finally:
#         print("\nSafely disconnecting hardware...")
#         spincoater.disconnect()

class Standalone_Worker_SpincoaterLiquidhandler(Worker_SpincoaterLiquidHandler):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def prime(self):
        self.loop = asyncio.new_event_loop()
        # self.queue = asyncio.PriorityQueue()
        # self.setup_logger(self.name)
    async def spincoat(self, sample, details):
        """executes a series of spin coating steps. A final "stop" step is inserted
        at the end to bring the rotor to a halt.

        Args:
            recipe (SpincoatRecipe): recipe of spincoating steps + drop times

        Returns:
            record: dictionary of recorded spincoating process.
        """
        print(f"\tstarting Spincoat of {sample['name']}")
        self.liquidhandler.server._start_directly()  # connect to liquid handler websocket
        # self.liquidhandler.server._protocol_context.comment(f"START `spincoat` step for sample {sample['name']}")
        # self.liquidhandler.server.mark_spincoat_start(sample_name = sample['name'])
        print(f"\tliquidhandler.server._start_directly() finished compiling")
        t0 = self.maestro.nist_time
        self.spincoater.start_logging()
        ### set up liquid handler tasks
        if len(details["drops"]) == 1:
            headstart, liquidhandlertasks = self._generatelhtasks_onedrop(
                t0=t0, drop=details["drops"][0]
            )
        else:  # assume two drops, planning does not allow for >2
            headstart, liquidhandlertasks = self._generatelhtasks_twodrops(
                t0=t0, drop0=details["drops"][0], drop1=details["drops"][1]
            )
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            tasks_future = await asyncio.gather(
                self._monitor_droptimes(liquidhandlertasks, t0),
                self._set_spinspeeds(details["steps"], t0, headstart),
                return_exceptions = True
            )

            # def future_callback(future):
            #     try:
            #         future.result()
            #     except Exception as e:
            #         self.logger.exception(f"Exception in {self}")
            #         # if future.exception(): #your long thing had an exception
            #         #     self.logger.error(f'Exception in {self}: {future.exception()}')

            # tasks_future.add_done_callback(future_callback)
            print(f"these are the tasks we need to do:\n{tasks_future}")
            print(f"{t0-self.maestro.nist_time:.2f} starting the deposition tasks")
            results = loop.run_until_complete(tasks_future)
            drop_times = results[0]
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    print(f"Task{i} failed with exception: {res}")
            print(f"{t0-self.maestro.nist_time:.2f} finished all tasks")
            rpm_log = self.spincoater.finish_logging()
            print(f"{t0-self.maestro.nist_time:.2f} finished logging")
            # self.liquidhandler.server._protocol_context.comment(f"END`spincoat` step for sample {sample['name']}")
            # self.liquidhandler.server.mark_spincoater_start(sample_name = sample['name'])
            self.liquidhandler.server.stop()  # disconnect from liquid handler websocket
            print(f"{t0-self.maestro.nist_time:.2f} server stopped")
        except Exception as e:
            print(f"++Fatal exception during loop execution: {e}")
        finally:
            loop.close()

        
        return {
            "liquidhandler_timings": {**drop_times},
            "spincoater_log": {**rpm_log},
            "headstart": headstart,
        }


class SingleSpin:
    def __init__(self, simulate = False):
        # # 1. Define the Terminal Commands
        # parser = argparse.ArgumentParser(description="PASCAL Single Spin & Drop CLI")
        # parser.add_argument("--rpm", type=int, required=True, help="Spin speed in RPM")
        # parser.add_argument("--duration", type=int, required=True, help="Spin duration in seconds")
        # parser.add_argument("--accel", type=float, default=1000.0, help="Acceleration in RPM/s (default: 1000)")
        # parser.add_argument("--vol", type=float, required=True, help="Antisolvent volume in uL")
        # parser.add_argument("--drop_time", type=float, required=True, help="Seconds into the spin to drop antisolvent")
        
        # self.args = parser.parse_args()

        # 2. Initialize Hardware Directly
        print("Connecting to SpinCoater (ODrive)...")
        try:
            # We pass the dummy gantry and switch to isolate the spincoater testing
            self.gantry = DummyGantry()
            self.gripper = DummyGripper()
            # self.dummy_switch = DummySwitch()
            self.switchbox = Switchbox()
            self.characterization = DummyGantry()
            # Initialize. Note: regular_bootup=True will trigger the ODrive calibration sequence
            self.spincoater = SpinCoater(
                gantry=self.gantry, 
                switch=self.switchbox.Switch(constants["spincoater"]["switchindex"]), 
                regular_bootup=True)
        except Exception as e:
            print(f"Failed to connect to SpinCoater: {e}")
            return

        # Labware
        self.hotplates = {
            "Hotplate1": HotPlate(
                name="Hotplate1",
                version="hotplate_frg4inch",
                gantry=self.gantry,
                gripper=self.gantry,
                id=1,
                p0=constants["hotplates"]["hp1"]["p0"],
                sample_size = "square_10mm"
            ),
            "Hotplate2": HotPlate(
                name="Hotplate2",
                version="hotplate_frg4inch",
                gantry=self.gantry,
                gripper=self.gantry,
                id=2,
                p0=constants["hotplates"]["hp2"]["p0"],
                sample_size = "square_10mm"
            ),
            "Hotplate3": HotPlate(
                name="Hotplate3",
                version="hotplate_frg4inch",
                gantry=self.gantry,
                gripper=self.gantry,
                id=3,
                p0=constants["hotplates"]["hp3"]["p0"],
                sample_size = "square_10mm"
            ),
        }
        # 3. Create Dummy Maestro and Worker
        self.maestro = DummyMaestro(
            self.spincoater, 
            ""
            )
        self.maestro.gantry = self.gantry
        self.maestro.gripper = self.gripper
        self.maestro.characterization = self.characterization
        self.maestro.hotplates = self.hotplates
        self.maestro.storage = {
            "Tray1": SampleTray(
                name="Tray1",
                version="storage_v4",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["sampletray"]["p1"],
                sample_size = "square_10mm",
                testslots = [f"{row}{col}" for row in ['I', 'G', 'E', 'C', 'A'] for col in [1, 3, 5]]
            ),
            "Tray2": SampleTray(
                name="Tray2",
                version="storage_v4",
                gantry=self.gantry,
                gripper=self.gripper,
                p0=constants["sampletray"]["p2"],
                sample_size = "square_10mm",
                testslots = [f"{row}{col}" for row in ['I', 'G', 'E', 'C', 'A'] for col in [1, 3, 5]]
            ),
        }
        print("Connecting to Liquid Handler...")
        # liquidhandler = LiquidHandler() # Uncomment and adjust based on actual initialization
        if simulate:
            self.liquidhandler = None # Placeholder until Opentrons is imported
        else:
            self.liquidhandler = OT2()
        self.maestro.liquidhandler = self.liquidhandler
        # self.worker = Worker_SpincoaterLiquidHandler(maestro=self.maestro, planning=False)
        self.worker = Standalone_Worker_SpincoaterLiquidhandler(maestro = self.maestro, planning = False)
        # 4. Construct the "Details" Dictionary matching workers.py expectations
        self._details = {
            "steps": [
                {
                    # "rpm": self.args.rpm,
                    # "acceleration": self.args.accel, 
                    # "duration": self.args.duration

                    "rpm": 5000,
                    "acceleration": 2000, 
                    "duration": 50
                }
            ],
            "drops": [
                 # PSK/235uL pipette
                 {
                    # "time": self.args.drop_time,
                    "time": -5,
                    "volume": 60,
                    # "volume": self.args.vol,
                    "height": 2,
                    "rate": 80, # Default dispensing rate
                    "slow_travel": True,
                    "slow_retract": True,
                    "air_gap": True,
                    "touch_tip": True,
                    "blow_out": True,
                    "pre_mix": (3, 40),
                    "reuse_tip": False,
                    "solution": {"well": {"labware": "Tray_4mL", "well": "A1"}} # **Requires real labware keys**
                },
                # A.S./1000 uL pipette
                {
                    # "time": self.args.drop_time,
                    "time": 25,
                    "volume": 200,
                    "rate": 500, # Default dispensing rate
                    "height": 2, # Default drop height
                    "slow_travel": True,
                    "slow_retract": True,
                    "air_gap": True,
                    "touch_tip": False,
                    "pre_mix": (3, 100),
                    "reuse_tip": False,
                    "solution": {"well": {"labware": "Tray_15mL", "well": "C3"}} # **Requires real labware keys**
                }
            ]
        }
        self.ready_to_spin = False

    def get_ready_to_spin(self, ip):
        if ip is None:
            raise ValueError("Must give the Opentrons IP address in order to spincoat!")
        self.liquidhandler.server.ip = ip
        self.ready_to_spin = True
        self.worker.prime()
        self.worker.start()

    def update_step_settings(
            self,
            rpm,
            acceleration,
            duration
    ):
        step_settings = {
            "rpm": rpm,
            "acceleration": acceleration, 
            "duration": duration
        }
        for key, value in step_settings:
            if value != -1:
                if isinstance(value, numbers.Number):
                    self._details['steps'][0][key] = value
                else:
                    raise ValueError(f"{key} must be a numeric value")

        '''if rpm != -1:
            self._details['steps'][0]['rpm'] = rpm
        if acceleration != -1:
            self._details['steps'][0]['acceleration'] = acceleration
        if duration != -1:
            self._details['steps'][0]['duration'] = duration'''

    def update_drop_settings(
            self,
            drop_number,
            time,
            volume,
            rate, # Default dispensing rate
            slow_travel,
            slow_retract,
            air_gap,
            touch_tip,
            blow_out,
            pre_mix,
            reuse_tip,
            solution
    ):
        drop_settings = {
            "time": time,
            "volume": volume, 
            "rate": rate, 
            "slow_travel": slow_travel, 
            "slow_retract": slow_retract, 
            "air_gap": air_gap,
            "touch_tip": touch_tip, 
            "blow_out": blow_out, 
            "pre_mix": pre_mix, 
            "reuse_tip": reuse_tip, 
            "solution": solution
        }
        
        for key, value in drop_settings:
            if value != -1:
                if (key == "time" or key == "volume" or key == "rate") and isinstance(value, numbers.Number):
                    self._details['drops'][drop_number][key] = value
                else:
                    raise ValueError(f"{key} must be a numeric value")
                
                if (key == "slow_travel" or key == "slow_retract" or key == "air_gap"
                    or key == "touch_tip" or key == "reuse_tip") and isinstance(value, bool):
                    self._details['drops'][drop_number][key] = value
                else:
                    raise ValueError(f"{key} must be either True or False")
                
                if key == "pre_mix" and isinstance(value, tuple):
                    self._details['drops'][drop_number][key] = value
                else:
                    raise ValueError(f"{key} must be a tuple")
                
            # solution format check not written
            
                
        '''
        if time != -1:
            self._details['drops'][drop_number]['time'] = time
        if volume != -1:
            self._details['drops'][drop_number]['volume'] = volume
        if rate != -1:
            self._details['drops'][drop_number]['rate'] = rate
        if slow_travel != -1:
            self._details['drops'][drop_number]['slow_travel'] = slow_travel
        if slow_retract != -1:
            self._details['drops'][drop_number]['slow_retract'] = slow_retract
        if air_gap != -1:
            self._details['drops'][drop_number]['air_gap'] = air_gap
        if touch_tip != -1:
            self._details['drops'][drop_number]['touch_tip'] = touch_tip
        if blow_out != -1:
            self._details['drops'][drop_number]['blow_out'] = blow_out
        if pre_mix != -1:
            self._details['drops'][drop_number]['pre_mix'] = pre_mix
        if reuse_tip != -1:
            self._details['drops'][drop_number]['reuse_tip'] = reuse_tip
        if solution != -1:
            self._details['drops'][drop_number]['solution'] = solution
        '''

        

    def update_spin_settings(
            self,
            rpm = -1,
            acceleration = -1,
            duration = -1,
            drop_number = -1,
            time = -1,
            volume = -1,
            rate = -1, # Default dispensing rate
            slow_travel = -1,
            slow_retract = -1,
            air_gap = -1,
            touch_tip = -1,
            blow_out = -1,
            pre_mix = -1,
            reuse_tip = -1,
            solution = -1
            ):
        """
        Update the spincoat parameters for the next spin
        
        :param self: Description
        :param settings: Description
        """

        self.update_step_settings(self, rpm, acceleration, duration)
        if drop_number != -1:
            self.update_drop_settings(self, drop_number, time, volume, rate, slow_travel, slow_retract,
                             air_gap, touch_tip, blow_out, pre_mix, reuse_tip, solution)
        else:
            print("Drop number not specified; skipping drop updates. If updating anything other than rpm, acceleration, or duration, please specify which drop to update (0 or 1)")

        
        return print("Settings are updated, Happy Spincoating!")
    
    def spin(self):
        """
        Deposits a single anti-solvent perovskite deposition
        """
        if self.ready_to_spin:
            # 5. Execute using asyncio
            # print(f"\nExecuting {self._details['steps'][0]['rpm']} RPM for {self._details['steps'][0]['duration']}s with {self._details['drops'][0]['vol']}uL drop at {self._details['steps'][0]['drop_time']}s.")
            try:
                loop = asyncio.get_event_loop()
                # Pass a mock sample dictionary
                result = loop.run_until_complete(self.worker.spincoat(sample={"name": "Single_Drop_Test"}, details=self._details))
                # result = self.worker.spincoat(sample = {"name": "sample"}, details = self._details)
                print("\nProcess Complete! Log Data:")
                # print(result)
            except Exception as e:
                print(f"\nError during execution: {e}")
            finally:
                print("Spin done!")
                # print("\nSafely disconnecting hardware...")
                # self.spincoater.disconnect()
        else:
            raise ValueError("Not ready to spin, be sure to feed the OT2 IP Address into the `get_ready_to_spin(ip)` method!")
