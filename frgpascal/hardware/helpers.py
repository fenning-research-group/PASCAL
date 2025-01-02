import serial.tools.list_ports as lp
import sys
import subprocess
import re


def which_os():
    if sys.platform.startswith("win"):
        return "Windows"
    elif sys.platform.startswith("linux") or sys.platform.startswith("cygwin"):
        # this excludes your current terminal "/dev/tty"
        return "Linux"
    elif sys.platform.startswith("darwin"):
        return "Darwin"
    else:
        raise EnvironmentError("Unsupported platform")


def _get_port_windows(device_identifiers):
    for p in lp.comports():
        match = True
        for attr, value in device_identifiers.items():
            if getattr(p, attr) != value:
                match = False
        if match:
            return p.device
    raise ValueError("Cannot find a matching port!")


def _get_port_linux(serial_number):
    """
    finds port number for a given hardware serial number
    """
    for p in lp.comports():
        if p.serial_number and p.serial_number == serial_number:
            return p.device
    return None

def _calibrate(self, calibration_file):
    self.gantry.moveto(*(self.p0[:2] + [self.p0[2] + 5]))
    self.gantry.gui()
    self.coordinates = self.gantry.position
    # self.gantry.moverel(z=10, zhop=False)
    self.__calibrated = True
    with open(calibration_file, "w") as f:
        yaml.dump(self.coordinates.tolist(), f)

def __load_calibration(self, calibration_file):
    with open(calibration_file, "r") as f:
        self.coordinates = np.array(yaml.load(f, Loader=yaml.FullLoader))
    self.__calibrated = True


def get_port(device_identifiers):
    operatingsystem = which_os()
    if operatingsystem == "Windows":
        port = _get_port_windows(device_identifiers)
    elif operatingsystem == "Linux":
        port = _get_port_linux(device_identifiers["serialid"])

    if port is None:
        raise ValueError(f"Device not found!")
    return port


def get_ot2_ip():
    try:
        # Run `arp -a` and decode the output
        result = subprocess.check_output("arp -a", shell=True).decode()

        # Define regex patterns to identify an interface and dynamic IPs within `169.254.x.x` - always 169.354 because of USB-ethernet protocol
        interface_pattern = re.compile(r"Interface: (169\.254\.\d{1,3}\.\d{1,3})")
        ip_pattern = re.compile(
            r"(169\.254\.\d{1,3}\.\d{1,3})\s+\S+\s+dynamic", re.IGNORECASE
        )

        current_interface = None
        dynamic_ip = None

        for line in result.splitlines():
            # Check if the line defines a new interface in the `169.254.x.x` range
            interface_match = interface_pattern.search(line)
            if interface_match:
                current_interface = interface_match.group(1)
                continue

            # Check for dynamic IPs under the current interface
            if current_interface and current_interface.startswith("169.254"):
                ip_match = ip_pattern.search(line)
                if ip_match:
                    dynamic_ip = ip_match.group(1)
                    break  # Found the dynamic IP, exit the loop

        if dynamic_ip:
            return dynamic_ip
        else:
            print("No dynamic IP addresses found in the 169.254.x.x range.")
            return None
    except Exception as e:
        print(f"Error retrieving IP address: {e}")
        return None
