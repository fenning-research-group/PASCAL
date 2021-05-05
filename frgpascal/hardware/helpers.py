import serial.tools.list_ports as lp

def get_port(serial_number):
	'''
	finds port number for a given hardware serial number
	'''
	for p in lp.comports():
		if p.serial_number and p.serial_number == serial_number:
			return p.device
	raise ValueError(f'Device {serial_number} not found!')