import numpy as np
from aiohttp import web # You can install aiohttp with pip
import json
import threading
import asyncio

from gantry import Gantry
from spincoater import Spincoater
from liquidhandler import OT2Server
from hotplate import HotPlate
from sampletray import SampleTray

class Maestro:
	def __init__(self, gantryport = None, spincoaterport = None, hotplateport = None):
		# Constants
		self.ZHOPCLEARANCE = 50 #height (above breadboard) to raise to when moving gantry with zhop option on.
		self.SAMPLEWIDTH = 10 #mm
		self.SAMPLETOLERANCE = 2.5 #mm extra opening width

		# Workers
		self.gantry = Gantry(port = gantryport),
		self.spincoater = Spincoater(port = spincoaterport)
		self.liquidhandler = OT2Server()

		# Labware
		
		self.hotplate = Hotplate(
			name = 'Hotplate1',
			version = 'v1',
			gantry = self.gantry,
			# p0 = [None, None, None]

		)

		# Storage
		self.storage = SampleTray(
			name = 'SampleTray1',
			version = 'v1',
			num = 5, #number of substrates loaded
			gantry = self.gantry,
			# p0 = [None, None, None]
		)

		# Stock Solutions


		# Status

	### Physical Methods
	# Compound Movements
	def transfer_sample(self, p1, p2, zhop = True):
		self.open(self.SAMPLEWIDTH + self.SAMPLETOLERANCE)
		self.moveto(p1, zhop = zhop)
		self.close()
		self.moveto(p2, zhop = zhop)
		self.open(self.SAMPLEWIDTH + self.SAMPLETOLERANCE)

	def spincoat(self, conditions, drops):
		record = {
			'time':[],
			'rpm': [],
			'droptime': {d:None for d in drops}
			}

		next_step_time = 0
		time_elapsed = 0
		step_idx = 0

		drop_idx = 0
		drop_times = drops.values()
		drop_names = drops.keys()
		next_drop_time = drop_times[0]
		drop_moves = [self.drop_perovskite(), self.drop_antisolvent()]

		spincoat_completed = False
		start_time = time.time()
		while not spincoat_completed:
			time_elapsed = time.time() - start_time
			record['time'].append(time_elapsed)
			record['rpm'].append(self.spincoater.rpm)

			if time_elapsed >= next_step_time:
				speed = conditions[step_idx][0]
				acceleration = conditions[step_idx][1]
				duration = conditions[step_idx][2]

				self.spincoater.setspeed(speed, acceleration)
				next_step_time += duration	
			if time_elapsed >= next_drop_time:
				drop_moves[drop_idx]
				drop_idx += 1
				record['droptime'][drop_names[drop_idx]] = time_elapsed

			if drop_idx > len(drops) and step_idx > len(conditions):
				spincoat_completed = True

			time.sleep(self.spincoater.POLLINGRATE)

			
		self.spincoater.stop()

		return record

	# Complete Sample

	def execute()
# OT2 Communication + Reporting Server

class Reporter:
	def __init__(self, parent, host = '0.0.0.0', port = 80):
		self.host = host
		self.port = port
		self.loop = None
		self.parent = parent

	def start(self):
		if self.loop is None:
			self.loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self.loop)
		asyncio.ensure_future(self.main())
		self.thread = threading.Thread(
			target = self.loop.run_forever,
			args = ()
			)
		self.thread.start()

	def stop(self):
		asyncio.run(self.__stop_routine())
		# self.loop.stop()
		# self.loop.close()
		# asyncio.get_event_loop().stop()
		# asyncio.get_event_loop().close()


	async def __stop_routine(self):
		await self.site.stop()
		await self.runner.cleanup()

	def build_app(self):
		self.app = web.Application()
		self.app.router.add_post('/update', self.update)

	async def main(self):
		self.build_app()
		self.runner = web.AppRunner(self.app)
		await self.runner.setup()
		self.site = web.TCPSite(
			self.runner,
			host = self.host,
			port = self.port
			)
		await self.site.start()

	# async def close(self):
	# 	await self.runner.cleanup()
	# 	self.loop.close()

	async def update(self, request):
		"""
		This function serves POST /update.

		The request should have a json body with a "step" key that at some point
		has the value "done-aspirating".

		It will return a json message with appropriate HTTP status.
		"""
		try:
			body = await request.json()
		except json.JSONDecodeError:
			text = await body.text()
			print(f"Request was not json: {text}")
			return web.json_response(status=400, # Bad Request
									 data={'error': 'bad-request'})
		
		if 'step' not in body:
			print(f"Body did not have a 'step' key")
			return web.json_response(status=400, # Bad Request
									 data={'error': 'no-step'})
		if body['step'] == 'done-aspirating':
		   # Here you might for instance check a balance
		   # attached to the computer to validate apsiration
		   print("Robot is done aspirating")
		   return web.json_response(status=200, # OK
									data={'done': True})

		if body['step'] == 'query':
			return web.json_response(status=200, # OK
									data={'parent': self.parent})