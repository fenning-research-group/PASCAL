import serial
import time

class SpinCoater:
	def __init__(self, port = 'INSERTDEFAULTPORTHERE'):
		self.accelerationrange = (1,200) #rpm/s
		self.speedrange = (500, 7500) #rpm
		self.connect(port = port)
		self.unlock()

	def connect(self, port, **kwargs):
		self.__handle = serial.Serial(
			port = port,
			**kwargs
			)
		self.__handle.open()
		# routine to initialize spincoater 
		# - cycle ESC power
		# - pwm to low, 2 seconds
		# - pwm to high, x seconds
		# finish

	def disconnect(self):
		self.__handle.close()

	def lock(self):
		"""
		routine to lock rotor in registered position for sample transfer
		"""
		if self.locked:
			return

		self.setspeed(min(self.speedrange))
		time.sleep(1)
		self.setspeed(0, 1) #slowly decelerate to stop
		self.__handle.write(b'l') #send command to engage electromagnet
		time.sleep(5) #wait some time to ensure rotor has stopped and engaged with electromagnet

	def unlock(self):
		"""
		unlocks the rotor from registered position
		"""
		self.__handle.write(b'u') #send command to disengage electromagnet
		self.locked = False

	def setspeed(self, speed, acceleration = max(self.accelerationrange)):
		"""
		sends commands to arduino to set a target speed with a target acceleration

		speed - target angular velocity, in rpm
		acceleration - target angular acceleration, in rpm/second. always positive
		"""
		speed = int(speed) #arduino only takes integer inputs
		acceleration = int(acceleration) 

		if self.locked:
			self.unlock()

		self.__handle.write(b's{0:d},{1:d}/r'.format(speed, acceleration)) #send command to arduino. assumes arduino responds to "s{rpm},{acceleration}\r'

		#possible code to wait for confirmation response from arduino that speed was hit successfully

	def stop(self):
		"""
		stop rotation and locks the rotor in position
		"""
		self.setspeed(min(self.speedrange), 10)
		self.lock()

	def recipe(self, recipe):
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

			where speed = rpm, acceleration = rpm/s, duration = s

		"""
		for step in recipe:
			speed = step[0]
			acceleration = step[1]
			duration = step[2]
			self.setspeed(speed, acceleration)
			time.sleep(duration)
		self.stop()


