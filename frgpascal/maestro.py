# from termios import error
import numpy as np
import os
from aiohttp import web  # You can install aiohttp with pip
import json
import threading
import asyncio
import time
import yaml

from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper

# from frgpascal.hardware.spincoater import SpinCoater
from frgpascal.hardware.liquidhandler import OT2
from frgpascal.hardware.hotplate import HotPlate
from frgpascal.hardware.sampletray import SampleTray

# from frgpascal.hardware.characterizationline import CharacterizationLine


MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardware", "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class Maestro:
    def __init__(self, numsamples: int, samplewidth: float = 10):
        """Initialze Maestro, which coordinates all the PASCAL hardware

        Args:
            numsamples (int): number of substrates loaded in sampletray
            samplewidth (float, optional): width of the substrates (mm). Defaults to 10 (ie 1 cm).
        """

        # Constants
        self.SAMPLEWIDTH = samplewidth  # mm
        self.SAMPLETOLERANCE = constants["gripper"][
            "extra_opening_width"
        ]  # mm extra opening width
        self.IDLECOORDINATES = constants["gantry"][
            "idle_coordinates"
        ]  # where to move the gantry during idle times, mainly to avoid cameras.
        self.CATCHATTEMPTS = constants["gripper"][
            "catch_attempts"
        ]  # number of times to try picking up a sample before erroring out
        # Workers
        self.gantry = Gantry()
        self.gripper = Gripper()
        # self.spincoater = SpinCoater(
        #     gantry = self.gantry,
        #     p0 = constants['spincoater']['p0']
        #     )
        # self.liquidhandler = OT2()

        # Labware
        self.hotplate = HotPlate(
            name="Hotplate1",
            version="hotplate_SCILOGEX",  # TODO #3 move the version details into a yaml file, define version in hardwareconstants instead.
            gantry=self.gantry,
            gripper=self.gripper,
            p0=constants["hotplate"]["p0"],
        )
        self.storage = SampleTray(
            name="SampleTray1",
            version="storage_v2",  # TODO #3
            num=numsamples,  # number of substrates loaded
            gantry=self.gantry,
            gripper=self.gripper,
            p0=constants["sampletray"]["p0"],
        )
        # Stock Solutions

        # Status
        self.manifest = {}  # store all sample info, key is sample storage slot

    def calibrate(self):
        """Prompt user to fine tune the gantry positions for all hardware components"""
        for component in [self.hotplate, self.storage]:  # , self.spincoater]:
            self.release()  # open gripper to open width
            component.calibrate()

    def _load_calibrations(self):
        """Load previous gantry positions, assume that hardware hasn't moved since last time."""
        for component in [self.hotplate, self.storage]:  # , self.spincoater]:
            component._load_calibration()  # REFACTOR #4 make the hardware calibrations save to a yaml instead of pickle file

    ### Physical Methods
    # Compound Movements
    def transfer(self, p1, p2, zhop=True):
        self.release()
        self.gantry.moveto(p1, zhop=zhop)
        self.catch()
        self.gantry.moveto(p2, zhop=zhop)
        self.release()
        self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
        self.gripper.close()

    def spincoat(self, recipe, drops):
        """
        executes a series of spin coating steps. A final "stop" step is inserted
        at the end to bring the rotor to a halt.

        recipe - nested list of steps in format:

            [
                [speed, acceleration, duration],
                [speed, acceleration, duration],
                ...,
                [speed, acceleration, duration]
            ]

            where speed = rpm, acceleration = rpm/s, duration = s (including the acceleration ramp!)

        drops = dictionary with perovskite, antisolvent drop times (seconds relative to start of recipe)
            {
                'perovskite': 10,
                'antisolvent': 15
            }
        """
        record = {"time": [], "rpm": [], "droptime": {d: None for d in drops}}

        drop_idx = 0
        drop_times = list(drops.values())
        if (
            drop_times[0] < 0
        ):  # set negative drop time to drop before spinning, static spincoat.
            static_offset = -drop_times[0]
        else:
            static_offset = 0
        drop_names = list(drops.keys())
        next_drop_time = drop_times[0]
        drop_moves = [
            self.liquidhandler.drop_perovskite,
            self.liquidhandler.drop_antisolvent,
        ]

        next_step_time = 0 + static_offset
        time_elapsed = 0
        step_idx = 0

        spincoat_completed = False
        steps_completed = False
        drops_completed = False
        start_time = time.time()
        while not spincoat_completed:
            time_elapsed = time.time() - start_time
            record["time"].append(time_elapsed)
            record["rpm"].append(self.spincoater.rpm)

            if time_elapsed >= next_step_time and not steps_completed:
                if step_idx >= len(recipe):
                    steps_completed = True
                else:
                    speed = recipe[step_idx][0]
                    acceleration = recipe[step_idx][1]
                    duration = recipe[step_idx][2]

                    self.spincoater.setspeed(speed, acceleration)
                    next_step_time += duration
                    step_idx += 1
            if time_elapsed >= next_drop_time and not drops_completed:
                drop_moves[drop_idx]()
                record["droptime"][drop_names[drop_idx]] = time_elapsed
                drop_idx += 1
                if drop_idx >= len(drop_times):
                    drops_completed = True
                else:
                    next_drop_time = drop_times[drop_idx]

            if drops_completed and steps_completed:
                spincoat_completed = True

            time.sleep(self.spincoater.POLLINGRATE)

        self.spincoater.stop()

        return record

    def catch(self):
        """
        Close gripper barely enough to pick up sample, not all the way to avoid gripper finger x float
        """
        self.CATCHATTEMPTS = 3
        caught_successfully = False
        while not caught_successfully and self.CATCHATTEMPTS > 0:
            self.gripper.open(self.SAMPLEWIDTH - self.SAMPLETOLERANCE)
            if (
                not self.gripper.is_under_load()
            ):  # if springs not pulling on grippers, assume that the sample is grabbed
                caught_successfully = True
                break
            else:
                self.CATCHATTEMPTS -= 1
                # lets jog the gripper position and try again.
                self.release()
                self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
                self.gantry.moverel(z=-self.gantry.ZHOP_HEIGHT)

        if not caught_successfully:
            raise ValueError("Failed to pick up sample!")

    def release(self):
        """
        Open gripper barely enough to release sample
        """
        self.gripper.open(
            self.SAMPLEWIDTH + self.SAMPLETOLERANCE, slow=True
        )  # slow to prevent sample position shifting upon release

    def idle_gantry(self):
        """Move gantry to the idle position. This is primarily to provide cameras a clear view"""
        self.gantry.moveto(self.IDLECOORDINATES)
        self.gripper.close()

    # Complete Sample
    def run_sample(self, storage_slot, spincoat_instructions, hotplate_instructions):
        """
        storage_slot: slot name for storage location
        spincoat_instructions:
            {
                'source_wells': [
                                    [plate_psk, well_psk, vol_psk], 	 (stock/mix, name, uL)
                                    [plate_antisolvent, well_antisolvent, vol_antisolvent],
                                ],
                'recipe':   [
                                [speed, acceleration, duration], 	(rpm, rpm/s, s)
                                [speed, acceleration, duration],
                                ...,
                                [speed, acceleration, duration]
                            ],
                'drop_times':    [time_psk, time_antisolvent]	 (s)
            }

        hotplate_instructions:
            {
                'temperature': temp 	(C),
                'slot': slot name on hotplate,
                'duration': time to anneal 	(s)
            }
        """

        # aspirate liquids, move pipettes next to spincoater
        self.liquidhandler.aspirate_for_spincoating(
            psk_well=spincoat_instructions["source_wells"]["well_psk"],
            psk_volume=spincoat_instructions["source_wells"]["volume_psk"],
            antisolvent_well=spincoat_instructions["source_wells"]["well_antisolvent"],
            antisolvent_volume=spincoat_instructions["source_wells"][
                "volume_antisolvent"
            ],
        )

        # load sample onto chuck
        self.spincoater.lock()
        self.spincoater.vacuum_on()
        self.transfer(self.storage(storage_slot), self.spincoater())
        self.idle_gantry()

        # spincoat
        spincoating_record = self.spincoat(
            recipe=spincoat_instructions["recipe"],
            drops=spincoat_instructions["drop_times"],
        )

        # move sample to hotplate
        self.liquidhandler.cleanup()
        self.spincoater.vacuum_off()
        self.transfer(self.spincoater(), self.hotplate(hotplate_instructions["slot"]))
        self.spincoater.unlock()
        ### TODO - start timer for anneal removal

        self.idle_gantry()

        self.manifest[storage_slot] = {
            "hotplate": {"instructions": hotplate_instructions},
            "spincoat": {
                "instructions": spincoat_instructions,
                "record": spincoating_record,
            },
        }

    def __del__(self):
        self.liquidhandler.server.stop()


# OT2 Communication + Reporting Server

# class Reporter:
# 	def __init__(self, parent, host = '0.0.0.0', port = 80):
# 		self.host = host
# 		self.port = port
# 		self.loop = None
# 		self.parent = parent

# 	def start(self):
# 		if self.loop is None:
# 			self.loop = asyncio.new_event_loop()
# 		asyncio.set_event_loop(self.loop)
# 		asyncio.ensure_future(self.main())
# 		self.thread = threading.Thread(
# 			target = self.loop.run_forever,
# 			args = ()
# 			)
# 		self.thread.start()

# 	def stop(self):
# 		asyncio.run(self.__stop_routine())
# 		# self.loop.stop()
# 		# self.loop.close()
# 		# asyncio.get_event_loop().stop()
# 		# asyncio.get_event_loop().close()


# 	async def __stop_routine(self):
# 		await self.site.stop()
# 		await self.runner.cleanup()

# 	def build_app(self):
# 		self.app = web.Application()
# 		self.app.router.add_post('/update', self.update)

# 	async def main(self):
# 		self.build_app()
# 		self.runner = web.AppRunner(self.app)
# 		await self.runner.setup()
# 		self.site = web.TCPSite(
# 			self.runner,
# 			host = self.host,
# 			port = self.port
# 			)
# 		await self.site.start()

# 	# async def close(self):
# 	# 	await self.runner.cleanup()
# 	# 	self.loop.close()

# 	async def update(self, request):
# 		"""
# 		This function serves POST /update.

# 		The request should have a json body with a "step" key that at some point
# 		has the value "done-aspirating".

# 		It will return a json message with appropriate HTTP status.
# 		"""
# 		try:
# 			body = await request.json()
# 		except json.JSONDecodeError:
# 			text = await body.text()
# 			print(f"Request was not json: {text}")
# 			return web.json_response(status=400, # Bad Request
# 									 data={'error': 'bad-request'})

# 		if 'step' not in body:
# 			print(f"Body did not have a 'step' key")
# 			return web.json_response(status=400, # Bad Request
# 									 data={'error': 'no-step'})
# 		if body['step'] == 'done-aspirating':
# 		   # Here you might for instance check a balance
# 		   # attached to the computer to validate apsiration
# 		   print("Robot is done aspirating")
# 		   return web.json_response(status=200, # OK
# 									data={'done': True})

# 		if body['step'] == 'query':
# 			return web.json_response(status=200, # OK
# 									data={'parent': self.parent})
