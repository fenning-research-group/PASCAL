import serial
import time

class SpinCoater:
	def __init__(self, gantry, port = '/dev/ttyACM0'):
		#constants
		self.POLLINGRATE = .5 #query rate to arduino, in seconds
		# self.ACCELERATIONRANGE = (1,200) #rpm/s
		self.SPEEDRANGE = (1000, 9000) #rpm
		self.TERMINATOR = '\n'
		self.port = port
		self.BAUDRATE = 57600
		self.gantry = gantry
		self.locked = None
		self.connect() 
		self.unlock()

	def connect(self, **kwargs):
		self.__handle = serial.Serial(
			port = self.port, 
			baudrate=self.BAUDRATE,
			timeout = 2,
			**kwargs)

	def disconnect(self):
		self.__handle.close()

	def calibrate(self):
		self.gantry.open_gripper()
		self.gantry.gui()
		self.coordinates = self.gantry.position
		self.gantry.moverel(z = 10, zhop = False)
		self.gantry.close_gripper()
		

	def write(self, s):
		'''
		appends terminator and converts to bytes before sending message to arduino
		'''
		self.__handle.write(f'{s}{self.TERMINATOR}'.encode())
	

	@property
	def rpm(self):
		self.write(f'c') #command to read rpm
		self.__rpm = float(self.__handle.readline().strip())
		return self.__rpm

	@rpm.setter
	def rpm(self, rpm):
		if rpm == 0:
			self.stop()
		else:
			self.setspeed(rpm)

	def vacuum_on(self):
		self.write('i3') #send command to engage/open vacuum solenoid

	def vacuum_off(self):
		self.write('o3') #send command to disengage/close vacuum solenoid

	def lock(self):
		"""
		routine to lock rotor in registered position for sample transfer
		"""
		if not self.locked:
			self.write('i4') #send command to engage electromagnet
			self.locked = True

	def unlock(self):
		"""
		unlocks the rotor from registered position
		"""
		if self.locked:
			self.write('o4') #send command to disengage electromagnet
			# time.sleep(2) #wait some time to ensure rotor has unlocked before attempting to rotate 
			self.locked = False

	def setspeed(self, speed, acceleration = None):
		'''
		sends commands to arduino to set a target speed with a target acceleration

		speed - target angular velocity, in rpm
		acceleration - target angular acceleration, in rpm/second. 
		acceleration = int(acceleration) 
		'''	
		speed = int(speed) #arduino only takes integer inputs

		self.unlock()
		self.__handle.write(f'a{speed:d}'.encode()) 

		#send command to arduino. assumes arduino responds to "s{rpm},{acceleration}\r'


	def stop(self):
		"""
		stop rotation and locks the rotor in position
		"""
		self.write('z') # 
		time.sleep(2) #wait some time to ensure rotor has stopped and engaged with electromagnet
		self.lock()
		time.sleep(1)

	def recipe(self, recipe):
		
		record = {
			'time':[],
			'rpm': []
			}

		start_time = round(time.time()) #big ass number
		next_step_time = 0
		time_elapsed = 0
		# first step == true
		for step in recipe:
			speed = step[0]
			duration = step[1]

			# if first_step == true:


			# 	first_step == false
			# self.write('d') 
			self.setspeed(speed)
			next_step_time += duration

			while time_elapsed <= next_step_time:
				time_elapsed = time.time()-start_time
				record['time'].append(time_elapsed)
				record['rpm'].append(self.rpm)
				time.sleep(self.POLLINGRATE)

			# self.write('f')
		self.lock()

		return record
