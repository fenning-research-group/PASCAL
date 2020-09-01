import serial
import time
import re

class Gantry:
	def __init__(self, port):
		#communication variables
		self.port = port
		self.terminator = '\n'
		self.POLLINGDELAY = 0.05 #delay between sending a command and reading a response, in seconds
		self.connect(port = port)

		#gantry variables
		self.xlim = (10,797.0)
		self.ylim = (0,165.0)
		self.zlim = (0,136.0)
		self.position = [None, None, None] #start at None's to indicate stage has not been homed.
		self.__targetposition = [None, None, None] 
		self.GANTRYTIMEOUT = 15 #max time allotted to gantry motion before flagging an error, in seconds

		# self.moving = [False, False, False] #boolean flag to indicate whether the xyz axes are in motion or not

		#gripper variables
		self.gripperangle = None
		self.servoangle = None
		self.MAXANGLE = 130
		self.MINANGLE = 55
		self.MINWIDTH = 5
		self.MAXWIDTH = 33 #max gripper width, in mm

	#communication methods
	def connect(self, port):
		self._handle = serial.Serial(
			port = port,
			timeout = 1,
			baudrate = 115200
			)
		self.position = [None, None, None] #start at None's to indicate stage has not been homed.	
		self.write('G90')
		self.write('M92 X40.0 Y26.77 Z400.0')

	def disconnect(self):
		self._handle.close()
		del self._handle

	def write(self, msg):
		self._handle.write(f'{msg}{self.terminator}'.encode())
		time.sleep(self.POLLINGDELAY)
		output = []
		while self._handle.in_waiting:
			line = self._handle.readline().decode('utf-8').strip()
			if line != 'ok':
				output.append(line)
			time.sleep(self.POLLINGDELAY)
		return output

	def update(self):
		found_coordinates = False
		while not found_coordinates:
			output = self.write('M114') #get current position
			for line in output:
				if line.startswith('X:'):
					x = float(re.findall('X:(\S*)', line)[0])
					y = float(re.findall('Y:(\S*)', line)[0])
					z = float(re.findall('Z:(\S*)', line)[0])
					found_coordinates = True
					break
		self.position = [x,y,z]

	def update_gripper(self):
		found_coordinates = False
		while not found_coordinates:
			output = self.write('M280 P1') #get current servo position
			for line in output:
				if line.startswith('echo: Servo'):
					self.servoangle = float(re.findall('SERVO 0: (\S*)', line)[0]) #TODO - READ SERVO POSITION
					self.gripperwidth = self.__servo_angle_to_width(self.servoangle)
					found_coordinates = True
					break

	#gantry methods
	def gohome(self):
		self.write('G28 X Y Z')
		self.update()

	def premove(self, x, y, z):
		'''
		checks to confirm that all target positions are valid
		'''
		if x > self.xlim[1] or x < self.xlim[0]:
			return False
		if y > self.ylim[1] or y < self.ylim[0]:
			return False
		if z > self.zlim[1] or z < self.zlim[0]:
			return False

		self.__targetposition = [x,y,z]
		return True

	def moveto(self, x = None, y = None, z = None):
		'''
		moves to target position in x,y,z (mm)
		'''

		if x is None:
			x = self.position[0]
		if y is None:
			y = self.position[1]
		if z is None:
			z = self.position[2]

		if self.premove(x, y, z):
			self.write(f'G0 X{x} Y{y} Z{z}')
			return self._waitformovement()
		else:
			raise Exception('Invalid move - probably out of bounds')

	def moverel(self, x = 0, y = 0, z = 0):
		'''
		moves by coordinates relative to the current position
		'''
		x += self.position[0]
		y += self.position[1]
		z += self.position[2]
		self.moveto(x,y,z)

	def _waitformovement(self):
		'''
		confirm that gantry has reached target position. returns False if
		target position is not reached in time allotted by self.GANTRYTIMEOUT
		'''
		start_time = time.time()
		time_elapsed = time.time() - start_time
		self._handle.write(f'M400{self.terminator}'.encode())
		self.write(f'M18 E1 FinishedMoving{self.terminator}'.encode())
		reached_destination = False
		while not reached_destination and time_elapsed < self.GANTRYTIMEOUT:
			time.sleep(self.POLLINGDELAY)
			while self._handle.in_waiting:
				line = self.readline()
				if line == 'echo:FinishedMoving':
					self.update()
					if selfposition == self.__targetposition:
						reached_destination = True
				time.sleep(self.POLLINGDELAY)
			time_elapsed = time.time() - start_time

		return reached_destination

	#gripper methods
	def open_gripper(self, width = None):
		'''
		open gripper to width, in mm
		'''
		if width is None:
			width = self.MAXWIDTH

		angle = self.__width_to_servo_angle(width)
		self.write(f'M280 P0 S{angle}')
		# self.write('M400')

	def close_gripper(self):
		self.open_gripper(width = self.MINWIDTH)

	def __servo_angle_to_width(self, angle):
		'''
		convert servo angle (degrees) to gripper opening width (mm)
		'''
		if (angle > self.MAXANGLE) or (angle < self.MINANGLE):
			raise Exception(f'Angle {angle} outside acceptable range ({self.MINANGLE}-{self.MAXANGLE})')

		fractional_angle = (angle-self.MINANGLE) / (self.MAXANGLE-self.MINANGLE)
		width = fractional_angle * (self.MAXWIDTH - self.MINWIDTH) + self.MINWIDTH
		return width

	def __width_to_servo_angle(self, width):
		'''
		convert gripper width (mm) to servo angle (degrees)
		'''
		if (width > self.MAXWIDTH) or (width < self.MINWIDTH):
			raise Exception(f'Width {width} outside acceptable range ({self.MINWIDTH}-{self.MAXWIDTH})')

		fractional_width = (width - self.MINWIDTH) / (self.MAXWIDTH - self.MINWIDTH)
		angle = fractional_width*(self.MAXANGLE-self.MINANGLE) + self.MINANGLE
		return angle



