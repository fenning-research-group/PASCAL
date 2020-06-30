import serial
import numpy as np

class Gantry():
	def __init__(self, port):
		self.port = port
		self.xlim = (0,100)
		self.ylim = (0,100)
		self.zlim = (0,100)
		self.terminator = '\n'
		self.position = [None, None, None] #start at None's to indicate stage has not been homed.	

	def connect(self, port):
		self._handle = serial.Serial(
			port = port,
			timeout = 1,
			baudrate = 9600,
			terminator = 
			)
		self.position = [None, None, None] #start at None's to indicate stage has not been homed.	

	def disconnect(self):
		self._handle.close()
		del self._handle

	def write(self, msg):
		self._handle.write(b'{}{}'.format(msg, self.terminator))

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
			



