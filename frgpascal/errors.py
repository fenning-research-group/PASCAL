

class Error(Exception):
    """
    Base class for exceptions in this module
    """
    pass


class InstrumentError(Error):
    """
    Exception raised when trying to access a pyvisa instrument that is not connected

    Attributes
    ----------
    _resourceAddress: str
        The address of the resource
    _resourceName: str
        The name of the resource (instrument)
    _message: str
        An explanation of the error
    """
    def __init__(self, address: str, resource_name: str, message: str):
        """
        Parameters
        ---------
        address: str
            The address of the resource
        resource_name: str
            The name of the resource
        message: str
            The explanation of the error
        """
        self._resourceAddress = address
        self._resourceName = resource_name
        self._message = message

    @property
    def address(self) -> str:
        return self._resourceAddress

    @property
    def resource_name(self) -> str:
        return self._resourceName

    @property
    def message(self) -> str:
        return self._message


class HotplateError(InstrumentError):
    _heatingStatus = 1  # Not heating
    _temperatureSetpoint = 25

    def __init__(self, address: str, resource_name: str, message: str):
        super().__init__(address, resource_name, message)

    @property
    def heating_status(self) -> bool:
        return self._heatingStatus

    def set_heating_status(self, status: bool):
        self._heatingStatus = status

    @property
    def temperature_setpoint(self) -> int:
        return self._temperatureSetpoint

    def set_temperature_setpoint(self, setpoint: int):
        self._temperatureSetpoint = setpoint


class ConfigurationError(Error):
    """
    Base class for Configuration Errors

    Attributes
    ----------
    _message: str
        The explanation of the error
    """
    def __init__(self, message: str):
        """
        Parameters
        ---------
        message: str
            The explanation of the error.
        """
        self._message = message

    @property
    def message(self):
        return self._message


class BTSSystemConfigError(ConfigurationError):
    """
    A Class representing a System Configuration Error

    Attributes
    ----------
    _testUnits: int
        The number of test units in the system
    """
    def __init__(self, message: str, test_units: int):
        """
        Parameters
        ----------
        message: str
            The explanation of the error
        test_units: int
            The number of test units in the system
        """
        super().__init__(message=message)
        self._testUnits = test_units

    @property
    def test_units(self) -> int:
        return self._testUnits

class DLCPSystemConfigError(ConfigurationError):
    """
    A Class representing a System Configuration Error

    Attributes
    ----------
    _testUnits: int
        The number of test units in the system
    """
    def __init__(self, message: str):
        """
        Parameters
        ----------
        message: str
            The explanation of the error
        test_units: int
            The number of test units in the system
        """
        super().__init__(message=message)

class ArduinoError(InstrumentError):
    """
    This class represents an Arduino Error
    """
    def __init__(self, address: str, name: str, message: str):
        super().__init__(address=address, resource_name=name, message=message)


class ArduinoSketchError(ArduinoError):
    """
    This class represents an error caused by handling an Arduino Sketch

    Attributes
    ----------
    _sketchFile: str
        The sketch file that produced the error
    """
    _sketchFile: str = None

    def __init__(self, address: str, name: str, sketch_file: str, message: str):
        super().__init__(address=address, name=name, message=message)
        self._sketchFile = sketch_file

    @property
    def sketch_file(self) -> str:
        return self._sketchFile
