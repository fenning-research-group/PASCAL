import serial

class HotPlate:
	def __init__(self, port = 'INSERTDEFAULTPORTHERE'):
		self.tlim = (20, 400) #temperature range, celsius
		self.connect(port = port)

	@property
	def temperature(self):
		self.__handle.write(b'GETTEMPERATURECOMMAND')
		temperature = self.__handle.readline()
		return float(temperature)
	
	@property
	def setpoint(self):
		self.__handle.write(b'GETSETPOINTCOMMAND')
		setpoint = self.__handle.readline()
		return float(setpoint)

	@setpoint.setter
	def setpoint(self, setpoint):
		if setpoint<min(self.tlim) or setpoint>max(self.tlim):
			print('Error: set temperature {} is out of range ({}, {})'.format(setpoint, *self.tlim))
		else:
			self.__handle.write(b'SETSETPOINTCOMMAND {0:.1f}'.format(setpoint))
	

	def connect(self, port, **kwargs):
		self.__handle = serial.Serial(
			port = port,
			**kwargs
			)
		self.__handle.open()

		
	def disconnect(self):
		self.__handle.close()		