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
from frgpascal.hardware.spincoater import SpinCoater
from frgpascal.hardware.liquidhandler import OT2
from frgpascal.hardware.hotplate import HotPlate
from frgpascal.hardware.sampletray import SampleTray
from frgpascal.hardware.characterizationline import CharacterizationLine
from frgpascal.experimentaldesign.recipes import SpincoatRecipe, AnnealRecipe, Sample

# from frgpascal.hardware.characterizationline import CharacterizationLine


MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardware", "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class Maestro:
    def __init__(
        self,
        numsamples: int = 1,
        samplewidth: float = 10,
        rootdir="C:\\Users\\Admin\\Desktop\\SampleExperiment",
    ):
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
        self.spincoater = SpinCoater(gantry=self.gantry)
        self.liquidhandler = OT2()
        self.characterization = CharacterizationLine(
            gantry=self.gantry, rootdir=rootdir
        )

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
            version="storage_v1",  # TODO #3
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
        for component in [
            self.hotplate,
            self.storage,
            self.spincoater,
            self.characterization.axis,
        ]:
            self.release()  # open gripper to open width
            component.calibrate()

    def gohome(self):
        threads = []
        for task in [
            self.gantry.gohome,
            self.characterization.axis.gohome,
            self.spincoater.connect,
        ]:
            thread = threading.Thread(target=task)
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()

    def _load_calibrations(self):
        """Load previous gantry positions, assume that hardware hasn't moved since last time."""
        for component in [
            self.hotplate,
            self.storage,
            self.spincoater,
            self.characterization.axis,
        ]:  # , self.spincoater]:
            component._load_calibration()  # REFACTOR #4 make the hardware calibrations save to a yaml instead of pickle file

    ### Physical Methods
    # Compound Movements
    def transfer(self, p1, p2, zhop=True):
        self.release()  # open the grippers
        self.gantry.moveto(p1, zhop=zhop)  # move to the pickup position
        self.catch()  # pick up the sample. this function checks to see if gripper picks successfully
        self.gantry.moveto(
            x=p2[0], y=p2[1], z=p2[2] + 5, zhop=zhop
        )  # move just above destination
        if self.gripper.is_under_load():
            raise ValueError("Sample dropped in transit!")
        self.gantry.moveto(p2, zhop=False)  # if not dropped, move to the final position
        self.release()  # drop the sample
        self.gantry.moverel(
            z=self.gantry.ZHOP_HEIGHT
        )  # move up a bit, mostly to avoid resting gripper on hotplate
        self.gripper.close()  # fully close gripper to reduce servo strain

    def spincoat(self, recipe: SpincoatRecipe):
        """executes a series of spin coating steps. A final "stop" step is inserted
        at the end to bring the rotor to a halt.

        Args:
            recipe (SpincoatRecipe): recipe of spincoating steps + drop times

        Returns:
            record: dictionary of recorded spincoating process.
        """

        perovskite_dropped = False
        antisolvent_dropped = False
        record = {}

        self.spincoater.start_logging()
        spincoating_in_progress = True
        t0 = time.time()
        tnext = 0
        for start_time, (rpm, acceleration, duration) in zip(
            recipe.start_times, recipe.steps
        ):
            tnext += start_time
            tnow = time.time() - t0  # time relative to recipe start
            while (
                tnow <= tnext
            ):  # loop and check for drop times until next spin step is reached
                if not perovskite_dropped and tnow >= recipe.perovskite_droptime:
                    self.liquidhandler.drop_perovskite
                    perovskite_dropped = True
                    record["perovskite_drop"] = tnow
                if not antisolvent_dropped and tnow >= recipe.antisolvent_droptime:
                    self.liquidhandler.drop_antisolvent
                    antisolvent_dropped = True
                    record["antisolvent_drop"] = tnow
                time.sleep(0.25)

            self.spincoater.set_rpm(rpm=rpm, acceleration=acceleration)

        self.spincoater.stop()
        record.update(self.spincoater.finish_logging())

        return record

    def catch(self):
        """
        Close gripper barely enough to pick up sample, not all the way to avoid gripper finger x float
        """
        self.CATCHATTEMPTS = 3
        caught_successfully = False
        while not caught_successfully and self.CATCHATTEMPTS > 0:
            self.gripper.close()
            self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
            self.gripper.open(self.SAMPLEWIDTH - 2)
            self.gripper.open(self.SAMPLEWIDTH - 1)
            time.sleep(0.1)
            if (
                not self.gripper.is_under_load()
            ):  # if springs not pulling on grippers, assume that the sample is grabbed
                caught_successfully = True
                break
            else:
                self.CATCHATTEMPTS -= 1
                # lets jog the gripper position and try again.
                self.gripper.close()
                self.gripper.open(self.SAMPLEWIDTH + self.SAMPLETOLERANCE, slow=False)
                # self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
                self.gantry.moverel(z=-self.gantry.ZHOP_HEIGHT)

        if not caught_successfully:
            self.gantry.moverel(z=self.gantry.ZHOP_HEIGHT)
            self.gripper.close()
            raise ValueError("Failed to pick up sample!")

    def release(self):
        """
        Open gripper slowly release sample without jogging position
        """
        self.gripper.open(
            self.SAMPLEWIDTH + self.SAMPLETOLERANCE, slow=True
        )  # slow to prevent sample position shifting upon release

    def idle_gantry(self):
        """Move gantry to the idle position. This is primarily to provide cameras a clear view"""
        self.gantry.moveto(self.IDLECOORDINATES)
        self.gripper.close()

    # Complete Sample
    # def run_sample(self, storage_slot, spincoat_instructions, hotplate_instructions):
    #     """
    #     storage_slot: slot name for storage location
    #     spincoat_instructions:
    #         {
    #             'source_wells': [
    #                                 [plate_psk, well_psk, vol_psk], 	 (stock/mix, name, uL)
    #                                 [plate_antisolvent, well_antisolvent, vol_antisolvent],
    #                             ],
    #             'recipe':   [
    #                             [speed, acceleration, duration], 	(rpm, rpm/s, s)
    #                             [speed, acceleration, duration],
    #                             ...,
    #                             [speed, acceleration, duration]
    #                         ],
    #             'drop_times':    [time_psk, time_antisolvent]	 (s)
    #         }

    #     hotplate_instructions:
    #         {
    #             'temperature': temp 	(C),
    #             'slot': slot name on hotplate,
    #             'duration': time to anneal 	(s)
    #         }
    #     """

    #     # aspirate liquids, move pipettes next to spincoater
    #     self.liquidhandler.aspirate_for_spincoating(
    #         psk_well=spincoat_instructions["source_wells"]["well_psk"],
    #         psk_volume=spincoat_instructions["source_wells"]["volume_psk"],
    #         antisolvent_well=spincoat_instructions["source_wells"]["well_antisolvent"],
    #         antisolvent_volume=spincoat_instructions["source_wells"][
    #             "volume_antisolvent"
    #         ],
    #     )

    #     # load sample onto chuck
    #     self.spincoater.lock()
    #     self.spincoater.vacuum_on()
    #     self.transfer(self.storage(storage_slot), self.spincoater())
    #     self.idle_gantry()

    #     # spincoat
    #     spincoating_record = self.spincoat(
    #         recipe=spincoat_instructions["recipe"],
    #         drops=spincoat_instructions["drop_times"],
    #     )

    #     # move sample to hotplate
    #     self.liquidhandler.cleanup()
    #     self.spincoater.vacuum_off()
    #     self.transfer(self.spincoater(), self.hotplate(hotplate_instructions["slot"]))
    #     self.spincoater.unlock()
    #     ### TODO - start timer for anneal removal

    #     self.idle_gantry()

    #     self.manifest[storage_slot] = {
    #         "hotplate": {"instructions": hotplate_instructions},
    #         "spincoat": {
    #             "instructions": spincoat_instructions,
    #             "record": spincoating_record,
    #         },
    #     }

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
