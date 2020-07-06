import serial
import numpy as np
import time

class Gantry():
	def __init__(self, port):
		#communication variables
		self.port = port
		self.POLLINGRATE = 0.1	#serial communication polling rate, in seconds
		self.terminator = '\n'

		#gantry variables
		self.xlim = (0,100)
		self.ylim = (0,100)
		self.zlim = (0,100)
		self.position = [None, None, None] #start at None's to indicate stage has not been homed.
		self.moving = [False, False, False] #boolean flag to indicate whether the xyz axes are in motion or not

		#gripper variables
		self.gripperangle = None
		self.OPENANGLE = 180
		self.CLOSEANGLE = 0

	#communication methods
	def connect(self, port):
		self._handle = serial.Serial(
			port = port,
			timeout = 1,
			baudrate = 9600
			)
		self.position = [None, None, None] #start at None's to indicate stage has not been homed.	

	def disconnect(self):
		self._handle.close()
		del self._handle

	def write(self, msg):
		self._handle.write(b'{}{}'.format(msg, self.terminator))

 	def update(self):
 		self.write('q')
 		while self._handle.inwaiting:
 			l = ser.readline()
 			k, v == l.split(' ')
 			if k == 'GantryPosition':
 				self.position = v.split(',')
 			if k == 'GantryMoving':
 				self.moving = [v_ == 1 for v_ in v]
 			if k == 'GripperAngle':
 				self.gripperangle = v

	#gantry methods
	def premove(self, x, y, z):
		if self.position == [None, None, None]: # stage has not been homed yet
			return False
		if x > self.xlim[1] or x < self.xlim[0]:
			return False
		if y > self.ylim[1] or y < self.ylim[0]:
			return False
		if z > self.zlim[1] or z < self.zlim[0]:
			return False

		return True

	def moveto(self, x = None, y = None, z = None):
		if x is None:
			x = self.position[0]
		if y is None:
			y = self.position[1]
		if z is None:
			z = self.position[2]

		if self.premove(x, y, z):
			self.write('m{},{},{}'.format(x,y,z))

		if self._waitformovement():
			return True
		else
			return False

	def _waitformovement(self, timeout = 30):
		start_time = time.time()
		time_elapsed = time.time() - start_time

		reached_destination = False
		while not reached_destination and time_elapsed < timeout:
			self.update()
			if not any(self.moving):
				reached_destination = True
			time.sleep(self.POLLINGRATE)

		return reached_destination

	#gripper methods
	def catch(self):
		self._setgripperangle(self.OPENANGLE)

	def release(self):
		self._setgripperangle(self.CLOSEANGLE)

	def _setgripperangle(self, angle):
		self.write('g{}'.format(angle))



