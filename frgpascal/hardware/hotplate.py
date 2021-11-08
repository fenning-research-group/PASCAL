import serial
import numpy as np
import os
import yaml
from typing import List
from threading import Lock

from frgpascal.hardware.geometry import Workspace
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper

MODULE_DIR = os.path.dirname(__file__)
HOTPLATE_VERSIONS_DIR = os.path.join(MODULE_DIR, "versions", "hotplates")
AVAILABLE_VERSIONS = {
    os.path.splitext(f)[0]: os.path.join(HOTPLATE_VERSIONS_DIR, f)
    for f in os.listdir(HOTPLATE_VERSIONS_DIR)
    if ".yaml" in f
}
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    hotplateconstants = yaml.load(f, Loader=yaml.FullLoader)["hotplates"]


def available_versions(self):
    return AVAILABLE_VERSIONS


class OmegaHub:
    def __init__(self, port):
        self.connect(port=port)
        self.lock = Lock()  # for multithreaded access control

    def query(self, payload):
        with self.lock:
            self.__handle.write(payload)
            response = self.__handle.readline()
        return response

    def connect(self, port):
        self.__handle = serial.Serial()
        self.__handle.port = port
        self.__handle.timeout = 2
        self.__handle.parity = "E"
        self.__handle.bytesize = 7
        self.__handle.baudrate = 9600
        self.__handle.open()

        # configure communication bits
        self.__end = b"\r\n"  # end bit <etx>

        # read current setpoint
        # self.__setpoint = self.__setpoint_get()
        # self.__setpoint = None

        return True

    def disconnect(self):
        self.__handle.close()
        return True

    def get_temperature(self, address):
        numWords = 1

        payload = self.__build_payload(
            address=address, command=3, dataAddress=1000, content=numWords
        )
        response = self.query(payload)

        data = int(response[7:-4], 16) * 0.1  # response given in 0.1 C

        return round(
            data, 2
        )  # only give two decimals, rounding error gives ~8 decimal places of 0's sometimes

    def get_setpoint(self, address):
        numWords = 1

        payload = self.__build_payload(
            address=address, command=3, dataAddress=1001, content=numWords
        )
        response = self.query(payload)

        data = int(response[7:-4], 16) * 0.1  # response given in 0.1 C

        return data

    def set_setpoint(self, address, setpoint):
        setpoint = round(setpoint * 10)  # need to give integer values of 0.1 C

        payload = self.__build_payload(
            address=address, command=6, dataAddress=1001, content=setpoint
        )
        response = self.query(payload)

        if response == payload:
            return True
        else:
            return False

    ### helper methods
    def __numtohex(self, num):
        # return codecs.encode(str.encode('{0:02d}'.format(num)), 'hex_codec')
        return "{0:02X}".format(num).encode()

    def __build_payload(self, address, command, dataAddress, content):
        def calculateChecksum(payload):
            numHexValues = int(len(payload) / 2)
            hexValues = [
                int(payload[2 * i : (2 * i) + 2], 16) for i in range(numHexValues)
            ]
            checksum_int = (
                256 - sum(hexValues) % 256
            )  # drop the 0x convention at front, we only want the last two characters
            checksum = "{0:02X}".format(checksum_int)

            return str.upper(checksum).encode()

        payload = self.__numtohex(address)
        payload = payload + self.__numtohex(command)
        payload = payload + str.encode(str(dataAddress))
        payload = payload + "{0:04X}".format(content).encode()

        # calculate checksum from current payload
        chksum = calculateChecksum(payload)

        # complete the payload
        payload = payload + chksum
        payload = payload + self.__end
        payload = (
            b":" + payload
        )  # should start with ":", just held til the end to not interfere with checksum calculation

        return payload


class HotPlate(Workspace):
    def __init__(
        self,
        name,
        version,
        gantry: Gantry,
        gripper: Gripper,
        pid_hub: OmegaHub = None,
        pid_address: int = None,
        p0=[None, None, None],
    ):
        constants, workspace_kwargs = self._load_version(version)
        super().__init__(
            name=name,
            gantry=gantry,
            gripper=gripper,
            p0=p0,
            **workspace_kwargs,
        )
        xmean = np.mean([p[0] for p in self._coordinates.values()])
        ymean = np.mean([p[1] for p in self._coordinates.values()])
        self._centerproximity = {
            slot: np.linalg.norm([p[0] - xmean, p[1] - ymean])
            for slot, p in self._coordinates.items()
        }

        self.TLIM = (constants["temperature_min"], constants["temperature_max"])
        # only consider slots with blanks loaded
        self.slots = {
            slotname: {"coordinates": coord, "payload": None}
            for slotname, coord in self._coordinates.items()
        }
        self.emptyslots = list(self.slots.keys())
        self.filledslots = []
        self._capacity = len(self.slots)
        self.full = False

        xmean = np.mean([p[0] for p in self._coordinates.values()])
        ymean = np.mean([p[1] for p in self._coordinates.values()])
        self._centerproximity = {
            slot: np.linalg.norm([p[0] - xmean, p[1] - ymean])
            for slot, p in self._coordinates.items()
        }

        if pid_hub is None:
            if pid_address is not None:
                raise Exception(
                    "If pid_address is specified, a pid_hub must also be specified!"
                )
            self.pid_hub = None
            self.pid_address = None
        else:
            if pid_address is None:
                raise Exception(
                    "If pid_hub is specified, a pid_address must also be specified!"
                )
            self.pid_hub = pid_hub
            self.pid_address = pid_address

        self.setpoint = 25

    @property
    def setpoint(self):
        self.__setpoint = self.pid_hub.get_setpoint(address=self.pid_address)
        return self.__setpoint

    @setpoint.setter
    def setpoint(self, x):
        if self.pid_hub.set_setpoint(address=self.pid_address, setpoint=x):
            self.__setpoint = x
        else:
            self.__setpoint = self.pid_hub.get_setpoint(address=self.pid_address)
            print(
                "Error changing set point - set point is still {0} C".format(
                    self.__setpoint
                )
            )

    @property
    def temperature(self):
        return self.pid_hub.get_setpoint(address=self.pid_address)

    def get_open_slot(self):
        if len(self.emptyslots) == 0:
            raise ValueError("No empty slots!")

        centerproximity = [self._centerproximity[slot] for slot in self.emptyslots]
        closest_slot_to_center = [
            slot for _, slot in sorted(zip(centerproximity, self.emptyslots))
        ][0]
        return closest_slot_to_center

    def load(self, slot, sample):
        if slot not in self.slots:
            raise ValueError(f"{slot} is an invalid slot!")
        elif slot in self.filledslots:
            raise ValueError(f"{slot} is already filled!")
        else:
            self.slots[slot]["payload"] = sample
            self.emptyslots.remove(slot)
            self.filledslots.append(slot)

    def unload(self, slot=None, sample=None):
        if sample is not None:
            found_sample = False
            for k, v in self.slots.items():
                if v["payload"] == sample:
                    found_sample = True
                    slot = k
            if not found_sample:
                raise ValueError(
                    f"Sample {sample.name} is not currently on the hotplate!"
                )
        else:
            if slot is None:
                raise ValueError("No slot defined?")
            if slot not in self.slots:
                raise ValueError(f"{slot} is an invalid slot!")
            elif slot in self.emptyslots:
                raise ValueError(f"{slot} is already empty!")

        self.slots[slot]["payload"] = None
        self.filledslots.remove(slot)
        self.emptyslots.append(slot)
        return sample

    def _load_version(self, version):
        if version not in AVAILABLE_VERSIONS:
            raise Exception(
                f'Invalid tray version "{version}".\n Available versions are: {list(AVAILABLE_VERSIONS.keys())}.'
            )
        with open(AVAILABLE_VERSIONS[version], "r") as f:
            constants = yaml.load(f, Loader=yaml.FullLoader)
        workspace_kwargs = {
            "pitch": (constants["xpitch"], constants["ypitch"]),
            "gridsize": (constants["numx"], constants["numy"]),
            "z_clearance": constants["z_clearance"],
            "openwidth": constants["openwidth"],
        }
        if "testslots" in constants:  # override 4 corner default
            workspace_kwargs["testslots"] = constants["testslots"]
        return constants, workspace_kwargs

    def export(self, fpath):
        """
        routine to export tray data to save file. used to keep track of experimental conditions in certain tray.
        """
        return None


## module for communication with Omega temperature controller

# class HotPlate:
# 	def __init__(self, port = '/dev/ttyUSB0'):
# 			self.tlim = (20, 400) #temperature range, celsius
# 			self.connect(port = port)

# 	@property
# 	def temperature(self):
# 			self.__handle.write(b'GETTEMPERATURECOMMAND')
# 			temperature = self.__handle.readline()
# 			return float(temperature)

# 	@property
# 	def setpoint(self):
# 			self.__handle.write(b'GETSETPOINTCOMMAND')
# 			setpoint = self.__handle.readline()
# 			return float(setpoint)

# 	@setpoint.setter
# 	def setpoint(self, setpoint):
# 			if setpoint<min(self.tlim) or setpoint>max(self.tlim):
# 					print('Error: set temperature {} is out of range ({}, {})'.format(setpoint, *self.tlim))
# 			else:
# 					self.__handle.write(b'SETSETPOINTCOMMAND {0:.1f}'.format(setpoint))


# 	def connect(self, port, **kwargs):
# 			self.__handle = serial.Serial(
# 					port = port,
# 					**kwargs
# 					)
# 			self.__handle.open()


# 	def disconnect(self):
# 			self.__handle.close()


# class Hotplate:
#     """
#     This class represents a SCILOGEX hotplate

#     Attributes
#     ----------
#     _calibration: dict
#         A dictionary containing the polynomial coefficients 'a1', 'a2' and 'b' for the temperature calibtation
#     _configRequiredOptions: List[str]
#         The options that need to be read in the calibration file
#     _heatOn: bool
#         True if its currently heating, False otherwise
#     _hotplate: serial.Serial
#         A handle to the serial communication object with the hotplate
#     _hotplateConnected: bool
#         True if the serial communication object is open, false otherwise.
#     _logger: logging.Logger
#         A logger to handle the class messages.
#     _targetTemperature: int
#         The temperature setpoint in °C
#     _MAX_FAILED_CALLS: int
#         The maximum allowable number of retries to call a method that communicates with the hotplate when the call was
#         unsuccessful

#     Methods
#     -------
#     connect(self):
#         Opens the serial communication with the hotplate.

#     disconnect(self):
#         Closes the serial communication with the hotplate.

#     _checksum(query) -> np.uint8:
#         Returns a checksum to the hotplate query.

#     _write_query(self, query):
#         Writes a query to the hotplate using serial communication.

#     get_temperature_setpoint(self, failed_calls: np.uint8 = 0) -> float:
#         Returns the temperature set point for the hotplate.
#     """
#     _calibration = {'a1': 0.00112759470035273,
#                     'a2': 0.820085915455346,
#                     'b': 11.0122612663442}
#     _configRequiredOptions = ['a1', 'a2', 'b']
#     _heatOn = False
#     _hotplate: serial.Serial = None
#     _hotplateConnected = False
#     _logger: logging.Logger = None
#     _loggingLevels = {'NOTSET': logging.NOTSET,
#                       'DEBUG': logging.DEBUG,
#                       'INFO': logging.INFO,
#                       'WARNING': logging.WARNING,
#                       'ERROR': logging.ERROR,
#                       'CRITICAL': logging.CRITICAL}
#     _targetTemperature = 25
#     _MAX_FAILED_CALLS = 20

#     def __init__(self, port = '/dev/ttyUSB0', name='HP_1', **kwargs):
#         """
#         Parameters
#         ---------
#         address: str
#             The port to which the hotplate is connected
#         name: str
#             The name assigned to the hotplate
#         **kwargs:
#             keyword arguments
#         """
#         self._port = port
#         self._baudrate = 9600 #57600
#         # self.connect()
#         # baudrate = kwargs.get('baudrate', 9600)
#         # bytesize = kwargs.get('bitsize', 8)
#         # stopbits = kwargs.get('stopbits', 1)
#         # timeout = kwargs.get('timeout', 0.5)
#         self._debug = kwargs.get('debug', False)
#         # self._port = port
#         # self._hotplate = serial.Serial()
#         # self._baudrate = baudrate

#         self._name = name
#         self.connect()

#     # def connect(self):
#     #   self.__handle = serial.Serial(address = self.address, baudrate = self._baudrate, **kwargs)

#     # def disconnect(self):
#     #   self.__handle.close()

#     def connect(self, **kwargs):
#         self._hotplate = serial.Serial(port = self._port, baudrate=self._baudrate, bytesize=8, parity='N', stopbits=1, timeout=.5, **kwargs)
#         self._hotplate.bytesize = 8 #bytesize
#         self._hotplate.stopbits = 1 #stopbits
#         self._hotplate.timeout =  0.5 #timeout
#         # if not self._hotplateConnected:
#         #     self._hotplate.open()
#         #     self._hotplateConnected = True
#         # else:
#         #     msg = "Hotplate '{0}' already open on address '{1}'.".format(self._name, self._port)
#         #     self._print(msg=msg, level='WARNING')

#     def disconnect(self):
#         self._hotplate.close()
#         # if self._hotplateConnected:
#         #     self._hotplate.close()
#         #     self._hotplateConnected = False
#         # else:
#         #     msg: str = "Arduino board '{0}' already closed.".format(self._name)
#         #     self._print(msg=msg, level='WARNING')

#     @staticmethod
#     def _checksum(query) -> np.uint8:
#         return sum(query[1:]) % 256

#     def _write_query(self, query):
#         for q in query:
#             b = np.uint8(q)
#             self._hotplate.write(b)
#             time.sleep(0.05)
#         time.sleep(0.1)

#     # def get_temperature_setpoint(self, failed_calls: np.uint8 = 0) -> float:
#         """
#         Returns the temperature set point of the hotplate.

#         .. note::
#             From SCILOGEX\r\n
#             Section 3.3 Get status\r\n
#             \r\n
#             Command:\r\n
#             -------------------------------------------------------\r\n
#             1 | 2 | 3 | 4 | 5 | 6\r\n
#             -------------------------------------------------------\r\n
#             0xfe | 0xA2 | NULL | NULL | NULL | Check sum\r\n
#             -------------------------------------------------------\r\n
#             Response:\r\n
#             -------------------------------------------------------\r\n
#             1    | 2    | 3, 4, 5, 6, 7, 8, 9, 10 | 11\r\n
#             -------------------------------------------------------\r\n
#             0xfd | 0xA2 | Parameter1... 8         | Check sum\r\n
#             -------------------------------------------------------\r\n
#             Parameter5 - temp set(high)\r\n
#             Parameter6 - temp set(low)\r\n

#         Parameters
#         ----------
#         failed_calls: np.uint8
#             The number of times the function has been called unsuccessfully (default = 0)

#         Returns
#         -------
#         float
#             The temperature setpoint

#         Warnings
#         --------
#         Warning
#             If the method was called more than _MAX_FAILED_CALLS unsuccessfully.

#         """

#         # Prepare the query to the hotplate
#         query = [254, 162, 0, 0]
#         checksum = self._checksum(query)
#         query.append(checksum)
#         try:
#             self._write_query(query)
#             out = self._hotplate.read(11)
#             self._hotplate.flush()
#             if len([out]) > 0:
#                 # Get the value of the set temp HT and LT from the hotplate
#                 thl = out[6:7]
#                 # Transform the value into decimal
#                 val = 0
#                 n = len(thl)
#                 for i in range(n):
#                     val += 256**(n-i-1)*thl[i]
#                 set_temperature = val / 10
#             else:
#                 msg = 'Failed to read the temperature set point in {0} - {1}. '.format(self._name, self._port)
#                 failed_calls += 1
#                 if failed_calls <= self._MAX_FAILED_CALLS:
#                     msg += 'Trying again... (Attempt {0}/{1})'.format(failed_calls, self._MAX_FAILED_CALLS)
#                     time.sleep(0.1)
#                     set_temperature = self.get_temperature_setpoint(failed_calls=failed_calls)
#                     self._print(msg, level='WARNING')
#                 else:
#                     msg += 'Exceeded allowable number of attempts for {0} - {1}.'.format(failed_calls,
#                                                                                          self._MAX_FAILED_CALLS)
#                     raise Warning(msg)
#         except serial.SerialTimeoutException as e:
#             msg = 'Failed to read the temperature set point in {0} - {1}. '.format(self._name, self._port)
#             msg += e.strerror
#             if failed_calls <= self._MAX_FAILED_CALLS:
#                 msg += 'Trying again... (Attempt {0}/{1})'.format(failed_calls, self._MAX_FAILED_CALLS)
#                 self._print(msg, level='WARNING')
#                 time.sleep(0.1)
#                 set_temperature = self.get_temperature_setpoint(failed_calls=failed_calls)
#             else:
#                 msg += 'Exceeded allowable number of attempts for {0} - {1}.'.format(failed_calls,
#                                                                                      self._MAX_FAILED_CALLS)
#                 self._print(msg, level='ERROR')
#                 raise e
#         return set_temperature

#     # def get_heating_status(self, failed_calls: np.uint8 = 0) -> bool:
#     def get_heating_status_original(self):
#         """
#         Finds out if the hotplate is currently heating or not

#         .. note::
#             From SCILOGEX\r\n
#             Section 3.2 Get information\r\n
#             \r\n
#             Command:\r\n
#             -------------------------------------------------------\r\n
#             1   | 2    | 3    | 4    | 5    | 6\r\n
#             -------------------------------------------------------\r\n
#             0xfe | 0xA1 | NULL | NULL | NULL | Check sum\r\n
#             -------------------------------------------------------\r\n
#             Response: \r\n
#             -------------------------------------------------------\r\n
#             1   | 2    | 3,4,5,6,7,8,9,10 | 11\r\n
#             -------------------------------------------------------\r\n
#             0xfd | 0xA1 | Parameter1... 8  | Check sum\r\n
#             -------------------------------------------------------\r\n
#             Parameter3: temperature status (0: closed, 1: open)

#             Parameters
#             ----------
#             failed_calls: np.uint8
#                 The number of times the function has been called unsuccessfully (default = 0)

#         Warnings
#         --------
#         Warning
#             If the method was called more than _MAX_FAILED_CALLS unsuccessfully.
#         """
#         # Prepare the query to the hotplate
#         query = [254, 161, 0, 0]
#         checksum = self._checksum(query)
#         query.append(checksum)
#         try:
#             self._write_query(query)
#             out = self._hotplate.read(11)

#             # test_io = self._hotplate.read(11)
#             self._hotplate.flush()

#         # status: bool = bool(test_io) #

#         # sweep = print(test_io)

#             if len([out]) > 0:
#                 status: bool = bool(out[4]) #
#                 # status: bool = bool(out[2]) #

#             else:
#                 msg = 'Failed to read the status in {0} - {1}. '.format(self._name, self._port)
#                 failed_calls += 1
#                 if failed_calls <= self._MAX_FAILED_CALLS:
#                     msg += 'Trying again... (Attempt {0}/{1})'.format(failed_calls, self._MAX_FAILED_CALLS)
#                     self._print(msg, level='WARNING')
#                     return self.get_heating_status(failed_calls=failed_calls)
#                 else:
#                     msg += 'Exceeded allowable number of attempts for {0} - {1}.'.format(failed_calls,
#                                                                                          self._MAX_FAILED_CALLS)
#                     raise Warning(msg)
#         except serial.SerialTimeoutException as e:
#             msg = 'Failed to read the temperature set point in {0} - {1}. '.format(self._name, self._port)
#             msg += e.strerror
#             if failed_calls <= self._MAX_FAILED_CALLS:
#                 msg += 'Trying again... (Attempt {0}/{1})'.format(failed_calls, self._MAX_FAILED_CALLS)
#                 self._print(msg, level='WARNING')
#                 time.sleep(0.1)
#                 return self.get_heating_status(failed_calls=failed_calls)
#             else:
#                 msg += 'Exceeded allowable number of attempts for {0} - {1}.'.format(failed_calls,
#                                                                                      self._MAX_FAILED_CALLS)
#                 self._print(msg, level='ERROR')
#                 raise e
#         return status

#     def get_heating_status(self):
#         # Prepare the query to the hotplate
#         # query = [254, 161, 0, 0]
#         # checksum = self._checksum(query)

#         # query.append(checksum)

#         write_io = self._hotplate.write((b'FEA1000000A1'))
#         test_io = self._hotplate.read()
#         status = test_io
#         # status: bool = bool(test_io) #

#         # try:
#         #     self._write_query(query)
#         #     self.
#         #     out = self._hotplate.read(11)

#         #     # test_io = self._hotplate.read(11)
#         #     self._hotplate.flush()

#         # # status: bool = bool(test_io) #

#         # # sweep = print(test_io)

#         #     if len([out]) > 0:
#         #         status: bool = bool(out[4]) #
#         #         # status: bool = bool(out[2]) #

#         #     else:
#         #         msg = 'Failed to read the status in {0} - {1}. '.format(self._name, self._port)
#         #         failed_calls += 1
#         #         if failed_calls <= self._MAX_FAILED_CALLS:
#         #             msg += 'Trying again... (Attempt {0}/{1})'.format(failed_calls, self._MAX_FAILED_CALLS)
#         #             self._print(msg, level='WARNING')
#         #             return self.get_heating_status(failed_calls=failed_calls)
#         #         else:
#         #             msg += 'Exceeded allowable number of attempts for {0} - {1}.'.format(failed_calls,
#         #                                                                                  self._MAX_FAILED_CALLS)
#         #             raise Warning(msg)
#         # except serial.SerialTimeoutException as e:
#         #     msg = 'Failed to read the temperature set point in {0} - {1}. '.format(self._name, self._port)
#         #     msg += e.strerror
#         #     if failed_calls <= self._MAX_FAILED_CALLS:
#         #         msg += 'Trying again... (Attempt {0}/{1})'.format(failed_calls, self._MAX_FAILED_CALLS)
#         #         self._print(msg, level='WARNING')
#         #         time.sleep(0.1)
#         #         return self.get_heating_status(failed_calls=failed_calls)
#         #     else:
#         #         msg += 'Exceeded allowable number of attempts for {0} - {1}.'.format(failed_calls,
#         #                                                                              self._MAX_FAILED_CALLS)
#         #         self._print(msg, level='ERROR')
#         #         raise e
#         return status

#     # def set_temperature(self, temperature: int, failed_calls: np.uint8 = 0):
#     #     """
#     #     Changes the temperature set point

#     #     .. note:
#     #          From SCILOGEX \r\n
#     #          3.5 Temperature control \r\n
#     #          Command: \r\n
#     #          -------------------------------------------------------\r\n
#     #           1   | 2    | 3          | 4         | 5    | 6 \r\n
#     #          -------------------------------------------------------\r\n
#     #          0xfe | 0xB2 | Temp(high) | temp(low) | NULL | Check sum \r\n
#     #          -------------------------------------------------------\r\n
#     #          Response: \r\n
#     #          -------------------------------------------------------\r\n
#     #           1   | 2    | 3          | 4    | 5    | 6 \r\n
#     #          -------------------------------------------------------\r\n
#     #          0xfd | 0xB2 | Parameter1 | NULL | NULL | Check sum \r\n
#     #          -------------------------------------------------------\r\n
#     #          If temperature set=300, temphigh)=0x01 temp (low)=0x2C  \r\n
#     #          ********** NOTE: sets T=30 °C not 300 °C \r\n
#     #          Parameter1: \r\n
#     #          0:OK \r\n
#     #          1:fault \r\n

#     #     Parameters
#     #     ----------
#     #     temperature: int
#     #         The new temperature set point
#     #     failed_calls: np.uint8
#     #         The number of times the function has been called unsuccessfully (default = 0)

#     #     Raises
#     #     ------
#     #     errors.HotplateError
#     #         If exceeded the maximum number of allowed attempts (_MAX_FAILED_CALLS) to set the temperature.
#     #     """
#     #     current_setpoint = self.get_temperature_setpoint()
#     #     corrected_temperature = self.correct_temperature_setpoint(temperature)
#     #     if current_setpoint != temperature or self.get_heating_status():
#     #         # Need to multiply by 10 to get the right temp setpoint
#     #         set_temp = corrected_temperature / 10
#     #         ht = np.uint8(np.floor(set_temp/256))
#     #         lt = np.uint8(set_temp % 256)
#     #         query = [254, 178, ht, lt, 0]
#     #         checksum = self._checksum(query)
#     #         query.append(checksum)
#     #         try:
#     #             self._write_query(query)
#     #             out = self._hotplate.read(6)
#     #             self._hotplate.flush()
#     #             if len([out]) == 0 or out[2] == 1:
#     #                 msg = r'Failed to set the temperature to {0:d} °C on {1} - {2}. '.format(temperature,
#     #                                                                                          self._name, self._port)
#     #                 failed_calls += 1
#     #                 if failed_calls <= self._MAX_FAILED_CALLS:
#     #                     msg += 'Trying again... (Attempt {0}/{1})'.format(failed_calls, self._MAX_FAILED_CALLS)
#     #                     self._print(msg, level='WARNING')
#     #                     self.set_temperature(temperature, failed_calls)
#     #                 else:
#     #                     msg += 'Exceeded allowed number of attempts for {0} - {1}'.format(self._name, self._port)
#     #                     self._print(msg, level='ERROR')
#     #                     e = errors.HotplateError(self._port, self._name, msg)
#     #                     e.set_heating_status(self.get_heating_status())
#     #                     e.set_temperature_setpoint(temperature)
#     #                     raise e
#     #         except serial.SerialTimeoutException as e:
#     #             msg = r'Timeout error trying to set the temperature to {0:d} °C on {1} - {2}. '.format(temperature,
#     #                                                                                                    self._name,
#     #                                                                                                    self._port)
#     #             failed_calls += 1
#     #             if failed_calls <= self._MAX_FAILED_CALLS:
#     #                 msg += 'Trying again... (Attempt {0}/{1})'.format(failed_calls, self._MAX_FAILED_CALLS)
#     #                 self._print(msg, level='WARNING')
#     #                 self.set_temperature(temperature, failed_calls)
#     #             else:
#     #                 msg += 'Exceeded allowed number of attempts for {0} - {1}'.format(self._name, self._port)
#     #                 self._print(msg, level='ERROR')
#     #                 raise e
#     #         else:
#     #             msg = 'Temperature set for {0} - {1} to {2:d}. Attempts {3}/{4}'.format(self._name,
#     #                                                                                     self._port,
#     #                                                                                     temperature,
#     #                                                                                     failed_calls + 1,
#     #                                                                                     self._MAX_FAILED_CALLS)
#     #             self._print(msg)

#     # def set_calibration(self, a1: float, a2: float, b: float):
#     #     """
#     #     Sets the polynomial coefficients for the temperature calibtation

#     #     Parameters
#     #     ----------
#     #     a1: float
#     #         The coefficient to the second oder term
#     #     a2: float
#     #         The coefficient to the first order term
#     #     b: float
#     #         The zero order term
#     #     """
#     #     self._calibration = {'a1': a1,
#     #                          'a2': a2,
#     #                          'b': b}

#     # def load_calibration(self, config: configparser.ConfigParser):
#     #     """
#     #     Loads the calibration coefficients from an .ini file

#     #     Parameters
#     #     ----------
#     #     config: onfigparser.ConfigParser
#     #         The configuration parser

#     #     Raises
#     #     ------
#     #     ValueError
#     #         If the argument is not an instance of configparser.ConfigParser
#     #     """
#     #     if self._validate_config(config, self._configRequiredOptions):
#     #         self._calibration = {'a1': config.getfloat(self._name, 'a1'),
#     #                              'a2': config.getfloat(self._name, 'a2'),
#     #                              'b': config.getfloat(self._name, 'b')}

#     # def _validate_config(self, config: configparser.ConfigParser, required_options) -> bool:
#     #     """
#     #     Validates that the provided configuration file contains all the polynomial coefficients.

#     #     Parameters
#     #     ----------
#     #     config: configparser.ConfigParser
#     #         The configuration parser with the calibration coefficients
#     #     required_options:
#     #         The required fields in the calibration file.

#     #     Returns
#     #     -------
#     #     bool
#     #         True if the configuration is valid, false otherwise.
#     #     """
#     #     if not isinstance(config, configparser.ConfigParser):
#     #         raise TypeError('The configuration argument must be an instance of configparser.ConfigParser.')
#     #     if config.has_section(self._name):
#     #         for o in required_options[self._name]:
#     #             if not config.has_option(self._name, o):
#     #                 msg = 'Config file must have option \'{0}\' for \'{1}\''.format(o, self._name)
#     #                 raise errors.ConfigurationError(message=msg)
#     #     return True

#     # def correct_temperature_setpoint(self, temperature: float) -> float:
#     #     """
#     #     Uses the stored calibration coefficients to correct for the temperature setpoint in order to achieve the right
#     #     temperature setting.

#     #     Parameters
#     #     ----------
#     #     temperature: float
#     #         The target temperature in °C
#     #     Returns
#     #     -------
#     #     float
#     #         The corrected temperature to be used as the hotplate's set point.
#     #     """
#     #     x = temperature
#     #     a1: float = self._calibration['a1']
#     #     a2: float = self._calibration['a2']
#     #     b: float = self._calibration['b']
#     #     return a1*x*x + a2*x + b

#     # def set_logger(self, logger: logging.Logger):
#     #     """
#     #     Sets the logger to handle the class messages.

#     #     Parameters
#     #     ----------
#     #     logger: logging.Logger
#     #         The logger

#     #     Raises
#     #     ------
#     #     ValueError
#     #         If the argument is not an instance of logging.Logger.
#     #     """
#     #     if not isinstance(logger, logging.Logger):
#     #         raise ValueError('The argument should be an instance of logging.Logger.')
#     #     self._logger = logger

#     # def _print(self, msg: str, level="INFO"):
#     #     """
#     #     Prints a class message. If a logger is available, it handles the message through the logger instead.

#     #     Parameters
#     #     ----------
#     #     msg: str
#     #         The message
#     #     level: str
#     #         The level of the message (only used of a logger is available)
#     #     """
#     #     level_no = self._loggingLevels[level]
#     #     if self._logger is None:
#     #         print(msg)
#     #     elif isinstance(self._logger, logging.Logger):

#     #         self._logger.log(level_no, msg)

#     # def __del__(self):
#     #     self.set_temperature(25)
#     #     self.disconnect()
