import serial
import numpy as np
import os
import yaml
from threading import Lock

from frgpascal.hardware.geometry import Workspace
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper
from frgpascal.hardware.helpers import get_port

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
    """
    Returns the dictionary of available hotplate version configuration files.

    Returns
    -------
    dict
        Dictionary mapping version names to their respective file paths
    """
    return AVAILABLE_VERSIONS


class Omega:
    """
    Interface for the physical Omega PID temperature controller via serial communication.

    This class constructs, sends, and parses hexadecimal strings over a serial connection 
    to read temperatures and set target temperatures. Supports multithreading.

    Parameters
    ----------
    id : int
        The identifier for the hotplate (1, 2, or 3).
    port : str, optional
        The port for the serial connection. If None, it is auto-discovered.

    Attributes
    ----------
    setpoint : float
        The target temperature in Celsius.
    temperature : float
        The current physical temperature in Celsius.

    Raises
    ______
    ValueError
        If the provided hotplate ID is not 1 (green), 2 (pink), or 3 (blue). 
    
    >>> TODO: Add usage examples
    """
    def __init__(self, id: int, port: str = None):
        if id not in [1, 2, 3]:
            raise ValueError("Hotplate ID must be 1 (green), 2 (pink), or 3 (blue)!")
        self.address = 1  # this is 1 despite the hotplate ID!
        constants = hotplateconstants[f"hp{id}"]
        if port is None:
            self.port = get_port(constants["device_identifiers"])
        self.connect()
        self.lock = Lock()  # for multithreaded access control

    @property
    def setpoint(self):
        self.__setpoint = self.get_setpoint()
        return self.__setpoint

    @setpoint.setter
    def setpoint(self, x):
        if self.set_setpoint(setpoint=x):
            self.__setpoint = x
        else:
            self.__setpoint = self.get_setpoint()
            print(
                "Error changing set point - set point is still {0} C".format(
                    self.__setpoint
                )
            )

    @property
    def temperature(self):
        return self.get_temperature()

    def query(self, payload):
        """
        Send a hexadecimal signal over the serial connection and read the response.

        Parameters
        ----------
        payload : bytes
            The formatted hexadecimal command string to send to the controller.

        Returns
        -------
        bytes
            The raw response read from the controller.
        """
        with self.lock:
            self.__handle.write(payload)
            response = self.__handle.readline()
        return response

    def connect(self):
        """
        Initialize and open the serial connection to the Omega controller

        Returns
        -------
        bool
            True if the connection sequence completes successfully
        """
        self.__handle = serial.Serial()
        self.__handle.port = self.port
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
        """
        Close the active serial connection to the Omega controller

        Returns
        -------
        bool
            True if the disconnection sequence completes successfully
        """
        self.__handle.close()
        return True

    def get_temperature(self):
        """
        Returns the current physical temperature of the hotplate

        Returns
        -------
        float
            The current temperature in Celsius, rounded to two decimal places.
        """
        numWords = 1

        payload = self.__build_payload(
            address=self.address, command=3, dataAddress=1000, content=numWords
        )
        response = self.query(payload)

        data = int(response[7:-4], 16) * 0.1  # response given in 0.1 C

        return round(
            data, 2
        )  # only give two decimals, rounding error gives ~8 decimal places of 0's sometimes

    def get_setpoint(self):
        """
       Returns the current target temperature

        Returns
        -------
        float
            The active setpoint temperature in Celsius.
        """
        numWords = 1

        payload = self.__build_payload(
            address=self.address, command=3, dataAddress=1001, content=numWords
        )
        response = self.query(payload)

        data = int(response[7:-4], 16) * 0.1  # response given in 0.1 C

        return data

    def set_setpoint(self, setpoint):
        """
        Updates the target temperature of the controller

        Parameters
        ----------
        setpoint : float
            The new target temperature in Celsius.

        Returns
        -------
        bool
            True if the setpoint was successfully updated, False otherwise.
        """
        setpoint = round(setpoint * 10)  # need to give integer values of 0.1 C

        payload = self.__build_payload(
            address=self.address, command=6, dataAddress=1001, content=setpoint
        )
        response = self.query(payload)

        if response == payload:
            return True
        else:
            return False

    def autotune(self, setpoint: float, pid_channel: int):
        """
        Initiate the hardware PID autotuning sequence for a specific target temperature.

        Parameters
        ----------
        setpoint : float
            The target temperature for the autotune calibration.
        pid_channel : int
            The PID profile channel to assign the tuned values to.

        Returns
        -------
        bool
            True if the autotune command was successfully acknowledged.
        """
        self.set_setpoint(setpoint)

        # set PID channel

        # turn on autotuning
        payload = self.__build_payload(
            address=self.address, command=5, dataAddress="0813", content=0xFF00
        )
        response = self.query(payload)

        if response == payload:
            return True
        else:
            return False

    def _autotune_in_progress(self):
        """
        Check whether the controller is actively undergoing an autotune process.

        Returns
        -------
        bool
            True if an autotune sequence is currently running.
        """
        payload = self.__build_payload(
            address=self.address, command=2, dataAddress="0813", content=1
        )
        response = self.query(payload)
        if response.decode().strip()[-3] == "1":
            return True
        else:
            return False

    def _set_PIDchannel(self, pid_channel: int):
        """
        Select the active PID parameter profile channel on the controller.

        Parameters
        ----------
        pid_channel : int
            The channel index to select (0, 1, 2, 3, or 4 for auto).

        Returns
        -------
        bool
            True if the command was successfully acknowledged.
        
        Raises
        ------
        ValueError
            If the provided channel is not within the valid range of [0, 4].
        """
        if pid_channel not in [0, 1, 2, 3, 4]:
            raise ValueError("Only 0, 1, 2, 3, and 4 (auto) are valid PID channels!")

        payload = self.__build_payload(
            address=self.address, command=6, dataAddress="101C", content=pid_channel
        )
        response = self.query(payload)

        if response == payload:
            return True
        else:
            return False

    ### helper methods
    def __numtohex(self, num):
        """
        Convert an integer to a formatted hexadecimal byte string.

        Parameters
        ----------
        num : int
            The integer to convert.

        Returns
        -------
        bytes
            The encoded hexadecimal string.
        """
        # return codecs.encode(str.encode('{0:02d}'.format(num)), 'hex_codec')
        return "{0:02X}".format(num).encode()

    def __build_payload(self, address, command, dataAddress, content):
        """
        Construct the full serial command payload including checksum generation.

        Parameters
        ----------
        address : int
            The hardware address of the controller
        command : int
            The integer representing the command type (e.g., read vs write)
        dataAddress : int or str
            The targeted address
        content : int
            The data value being written or requested.

        Returns
        -------
        bytes
            The fully constructed and checksummed payload
        """
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
    """
    High-level thermal workspace object managing sample slots and temperature control.

    This class inherits from the geometry `Workspace` class to manage a 2D grid of 
    slots where substrates can be placed. It tracks which slots are empty or filled 
    and calculates proximity to the center for optimal thermal contact. 

    Parameters
    ----------
    name : str
        The designated name of the hotplate workspace.
    version : str
        The version string to look up physical layout configurations in the yaml files.
    gantry : Gantry, optional
        The gantry object used for coordinate calibrations.
    gripper : Gripper, optional
        The gripper object used for coordinate calibrations.
    id : int, optional
        The hardware ID used to initialize the Omega controller (1, 2, or 3).
    p0 : list, optional
        The [x, y, z] origin coordinates for the workspace grid.
    controller : Omega, optional
        A pre-initialized Omega controller object to use instead of creating a new one.
    """
    def __init__(
        self,
        name,
        version,
        gantry: Gantry = None,
        gripper: Gripper = None,
        id: int = None,
        p0=[None, None, None],
        controller = None,
    ):
        constants, workspace_kwargs = self._load_version(version)
        super().__init__(
            name=name,
            gantry=gantry,
            gripper=gripper,
            p0=p0,
            **workspace_kwargs,
        )
        if id is not None and controller is None:
            self.controller = Omega(id=id)
            self.controller._set_PIDchannel(
                4
            )  # auto select PID settings based on setpoint
        if id is not None and controller is not None:
            self.controller = controller
            self.controller._set_PIDchannel(4)
        xmean = np.mean([p[0] for p in self._coordinates.values()])
        ymean = np.mean([p[1] for p in self._coordinates.values()])
        self._centerproximity = {
            slot: np.linalg.norm([p[0] - xmean, p[1] - ymean])
            for slot, p in self._coordinates.items()
        }

        # self.TLIM = (constants["temperature_min"], constants["temperature_max"])
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

    def get_open_slot(self):
        """
        Find and return the available slot closest to the physical center of the plate.

        Returns
        -------
        str
            The name of the optimal empty slot.

        Raises
        ------
        ValueError
            If there are no empty slots available on the hotplate.
        """
        if len(self.emptyslots) == 0:
            raise ValueError("No empty slots!")

        centerproximity = [self._centerproximity[slot] for slot in self.emptyslots]
        closest_slot_to_center = [
            slot for _, slot in sorted(zip(centerproximity, self.emptyslots))
        ][0]
        return closest_slot_to_center

    def load(self, slot, sample):
        """
        Register a specific sample as occupying a designated slot on the hotplate.

        Parameters
        ----------
        slot : str
            The name of the slot to load.
        sample : dict or object
            The sample payload being placed into the slot.

        Raises
        ------
        ValueError
            If the requested `slot` does not exist in the hotplate geometry.
        ValueError
            If the requested `slot` is already occupied.
        """
        if slot not in self.slots:
            raise ValueError(f"{slot} is an invalid slot!")
        elif slot in self.filledslots:
            raise ValueError(f"{slot} is already filled!")
        else:
            self.slots[slot]["payload"] = sample
            self.emptyslots.remove(slot)
            self.filledslots.append(slot)

    def unload(self, slot=None, sample=None):
        """
        Remove a sample from a slot, marking the slot as empty and available.

        Can be called either by specifying the exact slot, or by providing the sample 
        object to automatically look up its slot.

        Parameters
        ----------
        slot : str, optional
            The name of the slot to empty.
        sample : object, optional
            The sample payload to locate and remove.

        Returns
        -------
        object
            The sample object that was removed.

        Raises
        ------
        ValueError
            If searching by `sample` and the sample is not found on the hotplate.
        ValueError
            If searching by `slot` and no slot parameter is provided.
        ValueError
            If the requested `slot` does not exist or is already empty.
        """
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
        """
        Load the physical geometry parameters from the respective version's YAML file.

        Parameters
        ----------
        version : str
            The version string to look up in the available configurations.

        Returns
        -------
        constants : dict
            The constants dictionary from the YAML file.
        workspace_kwargs : dict
            A parsed keyword arguments dictionary for initializing the workspace.

        Raises
        ------
        Exception
            If the specified `version` is not found in the available files list.
        """
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
        }
        if "testslots" in constants:  # override 4 corner default
            workspace_kwargs["testslots"] = constants["testslots"]
        return constants, workspace_kwargs

    def export(self, fpath):
        """
        routine to export tray data to save file. used to keep track of experimental conditions in certain tray.

        Parameters
        ----------
        fpath : str
            The file path to save the export to.

        Returns
        -------
        None
        """
        return None
