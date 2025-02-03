import serial.tools.list_ports as lp
import sys
import subprocess
import re
import wmi

# from test_usb_id import get_lds


def get_lds(vid, pid):
    # if len(sys.argv) < 3:
    #     print("Usage: python call_ldshash.py <VID> <ProdID>")
    #     sys.exit(1)

    # vid = sys.argv[1]
    # pid = sys.argv[2]

    # Path to the PowerShell script (assumed to be in the same directory)
    ps_script = r"C:\Users\Admin\Desktop\Get-LDSHash.ps1"

    # Build the command.
    # The -NoProfile and -ExecutionPolicy Bypass options help avoid policy issues.
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ps_script,
        "-VID",
        vid,
        "-ProdID",
        pid,
    ]

    try:
        # Run the PowerShell script and capture its output as text.
        output = subprocess.check_output(command, universal_newlines=True)
        output = output.strip()
        if output:
            print("LDS Hash(es) for device(s) with VID {} and PID {}:".format(vid, pid))
            print(output)
        else:
            print(
                "No devices with VID {} and PID {} that expose an LDS hash were found.".format(
                    vid, pid
                )
            )
    except subprocess.CalledProcessError as e:
        print("Error calling PowerShell script:")
        print(e.output)


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


# def _get_port_windows(device_identifiers):
#     print(lp.comports())
#     for p in lp.comports():
#         match = True
#         for attr, value in device_identifiers.items():
#             print(getattr(p, attr))
#             if getattr(p, attr) != value:
#                 match = False
#         if match:
#             print(p)
#             print(getattr(p, attr))
#             return p.device
#     raise ValueError("Cannot find a matching port!")

connected_devices = {}


def query_available_devices(vid, pid):
    """
    Query the system for devices matching the given VID and PID.
    The inputs vid and pid should be integers.

    Returns a list of device dictionaries. Each dictionary contains:
      - 'vid': the decimal VID (int)
      - 'pid': the decimal PID (int)
      - 'com_port': e.g. "COM3" (if found), else None
      - 'serial_number': a string extracted from the DeviceID (if available), else None
      - 'name': the device name from WMI
      - 'device_id': the full DeviceID string from WMI
    """
    # Convert to uppercase four-digit hex strings.
    vid_hex = format(vid, "04X")
    pid_hex = format(pid, "04X")
    c = wmi.WMI()
    available_devices = []

    for device in c.Win32_PnPEntity():
        # Check that the DeviceID exists and contains the proper VID/PID strings.
        if (
            device.DeviceID
            and f"VID_{vid_hex}" in device.DeviceID.upper()
            and f"PID_{pid_hex}" in device.DeviceID.upper()
        ):
            # Try to extract the COM port from the device name, if present.
            com_port = None
            if device.Name:
                match = re.search(r"\(COM(\d+)\)", device.Name, re.IGNORECASE)
                if match:
                    com_port = f"COM{match.group(1)}"

            # Extract the serial number from the DeviceID.
            serial_number = None
            if device.DeviceID:
                # If the DeviceID is in the FTDIBUS format, use regex to extract the serial number.
                # Example FTDIBUS DeviceID: FTDIBUS\VID_0403+PID_6015+DN066QRWA\0000
                if "FTDIBUS" in device.DeviceID.upper():
                    m = re.search(
                        r"VID_[0-9A-F]{4}\+PID_[0-9A-F]{4}\+([^\\]+)",
                        device.DeviceID.upper(),
                    )
                    if m:
                        serial_number = m.group(1)
                else:
                    # Typical USB devices have a DeviceID of the form:
                    # USB\VID_XXXX&PID_XXXX\<SERIAL_OR_UNIQUE_ID>
                    parts = device.DeviceID.split("\\")
                    if len(parts) >= 3:
                        serial_number = parts[-1]

            available_devices.append(
                {
                    "vid": vid,
                    "pid": pid,
                    "com_port": com_port,
                    "serial_number": serial_number,
                    "name": device.Name,
                    "device_id": device.DeviceID,
                }
            )
    return available_devices


def connect_device_by_identifier(vid, pid, identifier):
    """
    Connects to a device when an explicit identifier is provided.

    The third parameter (identifier) can be either:
      - A COM port string (e.g. "COM3") if it starts with "COM" (case-insensitive), or
      - A serial number.

    Parameters vid and pid are provided as strings in decimal; they are converted to integers.
    """
    vid_int = int(vid)
    pid_int = int(pid)
    available = query_available_devices(vid_int, pid_int)

    # Determine whether the identifier is a COM port or a serial number.
    if identifier.upper().startswith("COM"):
        id_type = "com_port"
        identifier_val = identifier.upper()
    else:
        id_type = "serial_number"
        identifier_val = identifier

    device = None
    for dev in available:
        if dev.get(id_type):
            # Compare case-insensitively.
            if dev.get(id_type).upper() == identifier_val.upper():
                device = dev
                break

    if not device:
        print(
            f"No device found matching {id_type} = {identifier_val} for VID {vid_int} and PID {pid_int}."
        )
        return None

    # print(
    #     f"Connecting to device: {device['name']} (COM: {device.get('com_port')}, Serial: {device.get('serial_number')})"
    # )

    # Record the connection in our global dictionary.
    key = (vid_int, pid_int)
    if key not in connected_devices:
        connected_devices[key] = []

    # Check if this device is already connected (match by COM port or serial number).
    for dev in connected_devices[key]:
        if (
            dev.get("com_port")
            and device.get("com_port")
            and dev["com_port"].upper() == device["com_port"].upper()
        ):
            print(f"Device is already connected ({identifier} port match).")
            return device
        if (
            dev.get("serial_number")
            and device.get("serial_number")
            and dev["serial_number"].upper() == device["serial_number"].upper()
        ):
            print(f"Device is already connected ({identifier} serial number match).")
            return device

    connected_devices[key].append(device)
    return device


def connect_device_by_vid_pid(vid, pid):
    """
    Connects to a device given only the VID and PID.

    The function queries available devices and then checks the global
    connected_devices dictionary to determine which devices have already been connected.
    In a situation where two devices share the same VID/PID, the device that has not
    been connected (its identifier is not in the dictionary) is chosen.

    Parameters vid and pid are provided as strings in decimal; they are converted to integers.
    """
    vid_int = int(vid)
    pid_int = int(pid)
    available = query_available_devices(vid_int, pid_int)
    # print(
    #     f"Found {len(available)} available device(s) for VID {vid_int} and PID {pid_int}."
    # )

    key = (vid_int, pid_int)
    already_connected_ids = set()
    if key in connected_devices:
        for dev in connected_devices[key]:
            # Prefer using the COM port if available; otherwise, use the serial number.
            if dev.get("com_port"):
                already_connected_ids.add(dev["com_port"].upper())
            elif dev.get("serial_number"):
                already_connected_ids.add(dev["serial_number"].upper())

    # Select devices that are not yet connected.
    remaining_devices = []
    for dev in available:
        identifier = None
        if dev.get("com_port"):
            identifier = dev["com_port"].upper()
        elif dev.get("serial_number"):
            identifier = dev["serial_number"].upper()

        if identifier and identifier in already_connected_ids:
            continue
        remaining_devices.append(dev)

    if not remaining_devices:
        print(
            f"All available devices for vid={vid} and pid={pid} are already connected."
        )
        raise ValueError("Cannot find a matching port!")
        return None

    # Connect to the first device that has not yet been connected.
    device = remaining_devices[0]
    # print(
    #     f"Connecting to device: {device['name']} (COM: {device.get('com_port')}, Serial: {device.get('serial_number')})"
    # )

    if key not in connected_devices:
        connected_devices[key] = []
    connected_devices[key].append(device)
    return device


def connect_device(vid, pid, identifier=None):
    """
    Connects to a device using the provided parameters and returns the COM port string.

    If three parameters are provided, the third parameter (identifier) is used to select the device.
    If only vid and pid are provided, the function will choose the unconnected device (if applicable).

    Returns:
        The COM port string (e.g. "COM72") if the connection is successful, or None if no device is found.
    """
    if identifier is not None:
        device = connect_device_by_identifier(vid, pid, identifier)
    else:
        device = connect_device_by_vid_pid(vid, pid)
    if device is not None:
        # print("Connected device details:")
        # print(device)
        # Return the COM port string from the device record.
        return device.get("com_port")
    else:
        print(
            f"No available device found to connect for\nvid={vid}\npid={pid}\nidentifier={identifier}"
        )
        raise ValueError("Cannot find a matching port!")
        return None


def _get_port_windows_new(device_identifiers):
    vid = device_identifiers["vid"]
    pid = device_identifiers["pid"]
    identifier = None
    if "serial_number" in device_identifiers:
        identifier = device_identifiers["serial_number"]
    if "com_port" in device_identifiers:
        identifier = device_identifiers["com_port"]
    return connect_device(vid, pid, identifier)


def _get_port_windows_old(device_identifiers):
    for p in lp.comports():
        match = True
        for attr, value in device_identifiers.items():
            if getattr(p, attr) != value:
                match = False
        if match:
            # print(p.device)
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


def get_port(device_identifiers):
    operatingsystem = which_os()
    if operatingsystem == "Windows":
        port = _get_port_windows_new(device_identifiers)

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
