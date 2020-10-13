import serial
import time

class SpinCoater:
	def __init__(self, port = 'INSERTDEFAULTPORTHERE'):
		#constants
		self.POLLINGRATE = 0.5 #query rate to arduino, in seconds
		self.ACCELERATIONRANGE = (1,200) #rpm/s
		self.SPEEDRANGE = (1000, 9000) #rpm


		self.connect(port = port)
		self.unlock()

	@property
	def rpm(self):
		self.write('c') #command to read rpm
		self.__rpm = float(self.__handle.readline().strip())
		return self.__rpm
	
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

	def write(self, s):
		'''
		appends terminator and converts to bytes before sending message to arduino
		'''
		self.__handle.write(f'{s}{terminator}'.encode())
 	
	def lock(self):
		"""
		routine to lock rotor in registered position for sample transfer
		"""
		if self.locked:
			return

		self.setspeed(min(self.SPEEDRANGE))
		time.sleep(1)
		self.setspeed(0, 1) #slowly decelerate to stop
		self.write('l') #send command to engage electromagnet
		time.sleep(2) #wait some time to ensure rotor has stopped and engaged with electromagnet
		self.locked = True

	def unlock(self):
		"""
		unlocks the rotor from registered position
		"""
		self.write('u') #send command to disengage electromagnet
		self.locked = False

	def setspeed(self, speed, acceleration = max(self.ACCELERATIONRANGE)):
		"""
		sends commands to arduino to set a target speed with a target acceleration

		speed - target angular velocity, in rpm
		acceleration - target angular acceleration, in rpm/second. always positive
		"""
		speed = int(speed) #arduino only takes integer inputs
		acceleration = int(acceleration) 

		if self.locked:
			self.unlock()

		self.__handle.write(f's{speed:d},{acceleration:d}') #send command to arduino. assumes arduino responds to "s{rpm},{acceleration}\r'

		#possible code to wait for confirmation response from arduino that speed was hit successfully

	def stop(self):
		"""
		stop rotation and locks the rotor in position
		"""
		self.setspeed(min(self.SPEEDRANGE), 1)
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
		record = {
			'time':[],
			'rpm': []
			}

		start_time = time.time()
		next_step_time = 0
		time_elapsed = 0
		for step in recipe:
			speed = step[0]
			acceleration = step[1]
			duration = step[2]

			while time_elapsed <= next_step_time:
				record['time'].append(time_elapsed)
				record['rpm'].append(self.rpm)
				time.sleep(self.POLLINGRATE)

			self.setspeed(speed, acceleration)
			next_step_time += duration
		self.stop()

		return record



