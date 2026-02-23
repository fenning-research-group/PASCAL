import argparse
import time
import asyncio

# Adjust these imports to match your actual file structure
from frgpascal.hardware.spincoater import SpinCoater
from frgpascal.workers import Worker_SpincoaterLiquidHandler

# Assuming you have the liquid handler class somewhere
# from frgpascal.hardware.liquidhandler import LiquidHandler 

class DummySwitch:
    """Mock switch to prevent vacuum errors if not testing the vacuum"""
    def on(self): pass
    def off(self): pass

class DummyGantry:
    """Mock gantry to satisfy SpinCoater __init__ without moving the arm"""
    pass 

class DummyMaestro:
    """A lightweight mock clock to bypass the full PASCAL planner"""
    def __init__(self, spincoater, liquidhandler):
        self.spincoater = spincoater
        self.liquidhandler = liquidhandler
        
    @property
    def nist_time(self):
        # The worker heavily relies on this property to sync drops perfectly
        return time.time()

def main():
    # 1. Define the Terminal Commands
    parser = argparse.ArgumentParser(description="PASCAL Single Spin & Drop CLI")
    parser.add_argument("--rpm", type=int, required=True, help="Spin speed in RPM")
    parser.add_argument("--duration", type=int, required=True, help="Spin duration in seconds")
    parser.add_argument("--accel", type=float, default=1000.0, help="Acceleration in RPM/s (default: 1000)")
    parser.add_argument("--vol", type=float, required=True, help="Antisolvent volume in uL")
    parser.add_argument("--drop_time", type=float, required=True, help="Seconds into the spin to drop antisolvent")
    
    args = parser.parse_args()

    # 2. Initialize Hardware Directly
    print("Connecting to SpinCoater (ODrive)...")
    try:
        # We pass the dummy gantry and switch to isolate the spincoater testing
        dummy_gantry = DummyGantry()
        dummy_switch = DummySwitch()
        
        # Initialize. Note: regular_bootup=True will trigger the ODrive calibration sequence
        spincoater = SpinCoater(gantry=dummy_gantry, switch=dummy_switch, regular_bootup=True)
    except Exception as e:
        print(f"Failed to connect to SpinCoater: {e}")
        return

    print("Connecting to Liquid Handler...")
    # liquidhandler = LiquidHandler() # Uncomment and adjust based on actual initialization
    liquidhandler = None # Placeholder until Opentrons is imported

    # 3. Create Dummy Maestro and Worker
    maestro = DummyMaestro(spincoater, liquidhandler)
    worker = Worker_SpincoaterLiquidHandler(maestro=maestro, planning=False)

    # 4. Construct the "Details" Dictionary matching workers.py expectations
    details = {
        "steps": [
            {
                "rpm": args.rpm,
                "acceleration": args.accel, 
                "duration": args.duration
            }
        ],
        "drops": [
            {
                "time": args.drop_time,
                "volume": args.vol,
                "rate": 100, # Default dispensing rate
                "height": 2, # Default drop height
                "slow_travel": False,
                "slow_retract": False,
                "air_gap": False,
                "touch_tip": False,
                "pre_mix": [0, 0],
                "reuse_tip": False,
                "solution": {"well": {"labware": "target_tray_name", "well": "A1"}} # **Requires real labware keys**
            }
        ]
    }

    # 5. Execute using asyncio
    print(f"\nExecuting {args.rpm} RPM for {args.duration}s with {args.vol}uL drop at {args.drop_time}s.")
    try:
        loop = asyncio.get_event_loop()
        # Pass a mock sample dictionary
        result = loop.run_until_complete(worker.spincoat(sample={"name": "Single_Drop_Test"}, details=details))
        print("\nProcess Complete! Log Data:")
        print(result)
    except Exception as e:
        print(f"\nError during execution: {e}")
    finally:
        print("\nSafely disconnecting hardware...")
        spincoater.disconnect()
