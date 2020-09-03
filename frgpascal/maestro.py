import numpy as np
import pyquaternion
from aiohttp import web # You can install aiohttp with pip
import json
import threading
import asyncio

# from .gantry import Gantry
# from .spincoater import Spincoater
# from .liquidhandle import OT2

class Maestro:
	def __init__(self):
		# Constants
		self.ZHOPCLEARANCE = 50 #height (above breadboard) to raise to when moving gantry with zhop option on.
		self.SAMPLEWIDTH = 25.4 #mm
		self.SAMPLETOLERANCE = 4 #mm extra opening width

		# Workers
		self.gantry = Gantry(port = 'dev/acmtty0/'),
		self.spincoater = Spincoater(port = 'dev/usbtty0')
		self.liquidhandler = OT2()

		# Labware
		self.breadboard = Workspace(
			name = 'breadboard',
			xsize = 25.4*15,
			ysize = 25.4*15,
			pitch = (25.4,25.4),
			offset = (12.7,12.7,10),
			gridsize = (15,15),
			testslots = ['A10', 'A1', 'G1']
			)
		self.hotplate = Labware(
			name = 'hotplate1',
			bottomleftslot = 'H2', # bottom left slot that labware is registered to on breadboard,
			parent = self.breadboard,
			xsize = 25.4*6,
			ysize = 25.4*6,
			pitch = (50,50),
			offset = (12.7,12.7,25.4*3),
			gridsize = (6,6)
			)

		# Storage
		self.storage = Labware(
			name = 'storage1',
			bottomleftslot = 'H10', # bottom left slot that labware is registered to on breadboard,
			parent = self.breadboard,
			xsize = 25.4*6,
			ysize = 25.4*3,
			pitch = (50,50),
			offset = (12.7,12.7,25.4*0.5),
			gridsize = (6,3)
			)

		# Stock Solutions


		# Status

	### Physical Methods
	@property
	def position(self):
		return self.breadboard.reverse_transform(self.gantry.position) # return gantryposition in breadboard coordinates

	# Single Movements
	def moveto(self, p, zhop = True):
		p_gantry = self.breadboard.transform(p) #convert breadboard coordinate to gantry coordinate
		if self.position[2] > self.ZHOPCLEARANCE and p[2] > self.ZHOPCLEARANCE:
			zhop = False #no need to zhop if entire movement is occuring above the clearance height anyways
		
		if zhop:
			self.gantry.moveto(z = p_gantry[2]) #move up
			self.gantry.moveto(x = p_gantry[0], y = p_gantry[1]) #move over
			self.gantry.moveto(*p_gantry) #move to target
		else:
			self.moveto(*p_gantry)
		while self.gantry.inmotion:
			time.sleep(0.01)

	def open(self):
		self.gantry.open_gripper(self.SAMPLEWIDTH + self.SAMPLETOLERANCE)

	def close(self):
		self.gantry.close_gripper()

	# Compound Movements
	def transfer_sample(p1, p2, zhop = True):
		self.open()
		self.moveto(p1, zhop = zhop)
		self.close()
		self.moveto(p2, zhop = zhop)
		self.open()

	def spincoat(conditions, drops):
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

	# OT2 Communication + Reporting Server

class Workspace:
	'''
	General class for defining planar workspaces. Primary use is to calibrate the coordinate system of this workspace to 
	the reference workspace to account for any tilt/rotation/translation in workspace mounting.
	'''
	def __init__(self, name, xsize, ysize, pitch, offset, gridsize, testslots = None, verticalclearance = 25):
		self.calibrated = False #set to True after calibration routine has been run
		# coordinate system properties
		self.size = (xsize, ysize)
		self.pitch = pitch
		self.offset = offset
		self.gridsize = gridsize
		self.verticalclearance = verticalclearance 	#vertical offset when calibrating points, in mm. ensures no crashing before calibration
		# self.pitch = (25.4, 25.4) 	#space between neighboring breadboard holes, mm, (x,y). assume constrained in xy plane @ z = 0
		# self.offset = (10, 10, 0)		#offset between workspace (0,0 0) and bottom-left breadboard hole, mm, (x,y,z)
		# self.gridsize = (25, 15)	#number of breadboard holes available, (x,y)
		self.__generate_coordinates()

		if testslots is None:
			testslots = []
			testslots.append(f'{self.__ycoords[0]}{self.__xcoords[0]}') 	#top left corner
			testslots.append(f'{self.__ycoords[-1]}{self.__xcoords[0]}') 	#bottom left corner
			testslots.append(f'{self.__ycoords[-1]}{self.__xcoords[-1]}')	#bottom right corner
		elif len(testslots) != 3:
			raise Exception('Must provide three test points, in list form [A1, A2,B3], etc')

		self.testslots = testslots
		self.testpoints = np.array([self.__coordinates[name] for name in testslots])

	def __generate_coordinates(self):
		def letter(num):
			#converts number (0-25) to letter (A-Z)
			return chr(ord('A') + num)

		self.__coordinates = {}
		self.__ycoords = [letter(self.gridsize[1]-yidx-1) for yidx in range(self.gridsize[1])]	#lettering +y -> -y = A -> Z
		self.__xcoords = [xidx+1 for xidx in range(self.gridsize[0])]								#numbering -x -> +x = 1 -> 100

		for yidx in range(self.gridsize[1]): #y 
			for xidx in range(self.gridsize[0]): #x
				name = f'{self.__ycoords[yidx]}{self.__xcoords[xidx]}' 
				relative_position = [xidx*self.pitch[0], yidx*self.pitch[1], 0]
				self.__coordinates[name] = [p + poffset for p, poffset in zip(relative_position, self.offset)]

	def slot_coordinates(self, name):
		return self.transform(self.__coordinates[name])

	def calibrate(self, measuredpoints):
		measuredpoints = np.array(measuredpoints)
		u1 = self.testpoints[0] - self.testpoints[1]
		v1 = self.testpoints[0] - self.testpoints[2]
		p1 = np.mean(self.testpoints, axis = 0) #centroid of 3 test points
		n1 = np.cross(u1, v1) # vector normal to test plane in workspace coordinates
		n1 /= np.linalg.norm(n1) #convert to unit vector

		u2 = measuredpoints[0] - measuredpoints[1]
		v2 = measuredpoints[0] - measuredpoints[2]
		p2 = np.mean(measuredpoints, axis = 0) #centroid
		n2 = np.cross(u2,v2) # vector normal to test plane in reference coordinates
		n2 /= np.linalg.norm(n2)


		dot = np.dot(n1,n2)
		if dot > 0.99999:
			self.R = pyquaternion.Quaternion() #normal vectors are essentially parallel, no rotation needed to align coordinate systems - return unit quaternion
		elif dot < -0.99999:
			self.R = pyquaternion.Quaternion(angle = np.pi, axis = [1,0,0]) #normal vectors are parallel but in opposite directions (this shouldnt really ever happen for us). return inverting quaternion
		else:
			self.R = pyquaternion.Quaternion(angle = dot, axis = np.cross(n1,n2)) #rotation quaternion to bring workspace coordinate system parallel to reference coordinate system
		self.T = p2 - p1 #translation vector to align workspace and reference coordinate systems
		self.meauredpoints = measuredpoints
		self.calibrated = True

	def transform(self, p):
		if not self.calibrated:
			raise Exception('Workspace has not yet been calibrated to reference coordinate system!')
		return self.R.rotate(p) + self.T

	def reverse_transform(self, p):
		if not self.calibrated:
			raise Exception('Workspace has not yet been calibrated to reference coordinate system!')
		return self.R.inverse.rotate(p) - self.T

class Labware(Workspace):
	def __init__(self, name, bottomleftslot, parent, xsize, ysize, pitch, offset, gridsize, testslots = None, verticalclearance = 25):
		offset = np.array(offset)
		parent_offset = np.array(parent.slot_coordinates(bottomleftslot))
		offset += parent_offset

		super().__init__(name, xsize, ysize, pitch, offset, gridsize, testslots, verticalclearance)
		self.parent = parent

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