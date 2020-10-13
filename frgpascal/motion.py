import serial

class Positioner:
	def __init__(self, port = 'INSERTDEFAULTPORTHERE'):
		self.xlim = (0, 1000) #max x travel range, mm
		self.ylim = (0, 500) #max y travel range, mm
		self.zlim = (0, 150) #max z travel range, mm
		self.zoffset = 50 # distance from lowest z position and the table surface, mm. offset between tool coordinate and realspace coordinate
		self.zclear = 100 # minimum z value (mm) ensuring no collisions during large x/y moves
		### Possible constants to use for travel time estimation
		#self.speed = 10 #top travel speed, mm/s
		#self.acceleration = 10 #top travel acceleration, mm/s^2

		self.connect(port = port)
		self.homed = False
		self.gohome()

	def connect(self, port, **kwargs):
		self.__handle = serial.Serial(
			port = port,
			**kwargs
			)
		self.__handle.open()
		
	def disconnect(self):
		self.__handle.close()


	def gohome(self):
		""" 
		executes homing routine
		"""
		self.position = (0,0,0)
		self.__handle.write(b'HOMECOMMAND')
		self.homed = True

		#some kind of feedback to confirm that the positioner has homed successfully

	def moveto(self, x = self.position[0], y = self.position[1], z = self.position[2]):
		"""
		moves to an x,y,z coordinate. if any coordinates are not supplied, defaults to current coordinate. 
		ie can only supply x,y if z move is not necessary
		"""
		if ~checkmove(x, y, z): 
			return #move is invalid

		self.__handle.write(b'MOVECOMMAND')

		#some kind of feedback to confirm that the positioner has reached its location

	def checkmove(self, x = self.position[0], y = self.position[1], z = self.position[2], x0 = self.position[0], y0 = self.position[1], z0 = self.position[2]):
		"""
		confirms that moving to a desired x,y,z coordinate is possible. If possible, returns estimate of travel time in seconds.
		x,y,z - target position, in mm
		x0, y0, z0 - starting position, in mm. used to estimate travel time
		"""

		#check if the target coordinate is within tool volume
		for axis, lim, label in zip([x,y,z], [self.xlim, self.ylim, self.zlim], ['x', 'y', 'z']):
			if axis<min(lim) or axis>max(lim):
				print('Error: target {3} position {0} out of range ({1}, {2})'.format(axis, *lim, label))
				return False

		#if we haven't already returned False, calculate travel time estimate and return that value

		dx = abs(x-x0)
		dy = abs(y-y0)
		dz = abs(z-z0)

		xtime = "some math here"
		ytime = "some math here"
		ztime = "some math here"

		return min([xtime, ytime, ztime]) #assuming that we can move all three axes simultaneously, we can treat the min axis travel time as total travel time.

class Gripper:
	def __init__(self, port = 'INSERTDEFAULTPORTHERE', slidewidth = 15):
		self.wlim = (0, 30) #range of clamping widths available, in mm
		self.slidewidth = slidewidth #slide width, in mm. used to define pick/release commands
		self.releaseclearance = 5 #how far to expand grippers to release slide, in mm
		self.connect()

	def connect(self, port, **kwargs):
		self.__handle = serial.Serial(
			port = port,
			**kwargs
			)
		self.__handle.open()
		
	def disconnect(self):
		self.__handle.close()


	def setwidth(self, width):
		"""
		brings gripper arms to a set distance apart, in mm
		"""
		if width<min(self.wlim) or width>max(self.wlim):
			print('Error: target width {} is out of range ({}, {})'.format(width, *self.wlim))
		else:
			self.__handle.write(b'SETWIDTHCOMMAND')

		# some routine to ensure width has been achieved

	def pick(self):
		self.setwidth(self.slidewidth)

	def release(self):
		self.setwidth(self.slidewidth + self.releaseclearance)

