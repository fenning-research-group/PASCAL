import numpy as np
from aiohttp import web
import asyncio
import time
import threading

class OT2Server:
	def __init__(self, parent, host = '0.0.0.0', port = 8080):
		self.host = host
		self.port = port
		self.parent = parent
		self.pending_requests = 0 #number of pending instructions for OT2
		self.requests = []
		self.OT2_status = 0 #0 = idle, 1 = task in progress, 2 = task completed, awaiting acknowledgement.
		self.taskid = None

	### protocol methods

	def add_to_queue(self, pipette, function, *args, **kwargs):
		payload = {
			'taskid': hash(time.time()),
			'pipette': pipette,
			'function': function,
			'args': args,
			'kwargs': kwargs
		}
		self.pending_requests += 1
		self.requests.append(payload)

	def send_request(self):
		payload = self.requests.pop(0) #take request from top of stack
		payload['pending_requests'] = self.pending_requests
		self.pending_requests -= 1

		return web.json_response(
			status=200, # OK
			data=payload
			)

	def idle_ack(self):
		return web.json_response(
			status=200, # OK
			data={'pending_requests':0}
			)
	def complete_ack(self):
		return web.json_response(
			status=200, # OK
			data={'pending_requests':self.pending_requests, 'taskid': self.taskid, 'completion_acknowledged': 1}
			)


	### webserver methods
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
		self.loop.call_soon_threadsafe(self.loop.stop)
		# self.loop.close()
		self.thread.join()
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
		

		self.OT2_status = body['status']

		# if 'step' not in body:
		# 	print(f"Body did not have a 'step' key")
		# 	return web.json_response(status=400, # Bad Request
		# 							 data={'error': 'no-step'})

		if body['status'] == 0: #OT2 idle, waiting for instructions
			if self.pending_requests:
				return self.send_request()
			else:
				return self.idle_ack()


		if body['status'] == 1: #task in progress
			self.taskid = body['taskid']

		if body['status'] == 2: #task completed
			self.taskid = None