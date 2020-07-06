import serial
import numpy as np
import time

class Spincoater():
	def __init__(self, port):
		self.port = port
		self.terminator = '\n'

		self.MINRPM = 0
		self.MAXRPM = 7000
		self.locked = False

	def connect(self, port):
		self._handle = serial.Serial(
			port = port,
			timeout = 1,
			baudrate = 9600
			)
		self.unlock()

	def disconnect(self):
		self._handle.close()
		del self._handle

	def write(self, msg):
		self._handle.write(b'{}{}'.format(msg, self.terminator))


	def setRPM(self, rpm):
		if self.locked:
			self.unlock()
		if rpm > self.MAXRPM:
			print('Target RPM {0} is out of achievable range [{1},{2}] - setting RPM at {2}'.format(rpm, self.MINRPM, self.MAXRPM))
			rpm = self.MAXRPM
		if rpm < self.MINRPM:
			print('Target RPM {0} is out of achievable range [{1},{2}] - setting RPM at {1}'.format(rpm, self.MINRPM, self.MAXRPM))
			rpm = self.MINRPM 		

		self.write('a{0:d}'.format(rpm))

	def lock(self):
	'''
	Locks the chuck into the home position
	Spins up the chuck to a low speed, then disengages and enables electromagnet
	to allow the chuck to coast into the home position + engage with the magnet
	'''
		self.setRPM(500)
		time.sleep(2)
		self.setRPM(0)
		self.write('l')
		self.locked = True

	def unlock(self):
		'''
		unlocks the chuck, allowing for rotation
		'''
		self.write('u')
		self.locked = False