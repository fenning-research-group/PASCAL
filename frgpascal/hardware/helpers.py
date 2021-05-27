import serial.tools.list_ports as lp
import sys

def which_os():
    if sys.platform.startswith('win'):
        return 'Windows'
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        return 'Linux'
    elif sys.platform.startswith('darwin'):
        return 'Darwin'
    else:
        raise EnvironmentError('Unsupported platform')

def get_port_windows(vendorid, productid):
    for p in lp.comports():
        if vendorid in p.hwid and productid in p.hwid:
            return p.device
    return None
def get_port_linux(serial_number):
    '''
    finds port number for a given hardware serial number
    '''
    for p in lp.comports():
        if p.serial_number and p.serial_number == serial_number:
            return p.device
    return None

def get_port(constants):
    operatingsystem = which_os()
    if operatingsystem == 'Windows':
        port = get_port_windows(constants['vendorid'], constants['productid'])
    elif operatingsystem == 'Linux':
        port = get_port_linux(constants['serialid'])

    if port is None:
        raise ValueError(f'Device not found!')
    return port