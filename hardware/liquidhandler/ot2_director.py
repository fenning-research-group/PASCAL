import numpy as np
from aiohttp import web
import asyncio

class OT2Server:
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