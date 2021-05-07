import string
import os
import yaml
from .geometry import Workspace

MODULE_DIR = os.path.dirname(__file__)
TRAY_VERSIONS_DIR = os.path.join(MODULE_DIR, "versions", "sampletrays")
AVAILABLE_VERSIONS = {
    os.path.splitext(f)[0]: os.path.join(TRAY_VERSIONS_DIR, f)
    for f in os.listdir(TRAY_VERSIONS_DIR)
}


class SampleTray(Workspace):
    def __init__(self, name, num, version, gantry=None, p0=[None, None, None]):
        constants, workspace_kwargs = self._load_version(version)
        super().__init__(name=name, gantry=gantry, p0=p0, **workspace_kwargs)

        # only consider slots with blanks loaded
        self.slots = {
            name: {"coordinates": coord, "payload": "blank substrate"}
            for _, (name, coord) in zip(range(num), self._coordinates.items())
        }

        self.__queue = iter(self.slots.keys())
        self.exhausted = False

    def __next__(self):
        nextslot = next(self.__queue, None)  # if no more slots left, return None
        if nextslot is None:
            self.exhausted = True

        return nextslot

    def _load_version(self, version):
        if version not in AVAILABLE_VERSIONS:
            raise Exception(
                f'Invalid tray version "{version}".\n Available versions are: {list(AVAILABLE_VERSIONS.keys())}.'
            )
        constants = yaml.load(AVAILABLE_VERSIONS[version], Loader=yaml.FullLoader)
        workspace_kwargs = {
            "pitch": (constants["xpitch"], constants["ypitch"]),
            "gridsize": (constants["numx"], constants["numy"]),
            "z_clearance": constants["z_clearance"],
            "openwidth": constants["openwidth"],
        }
        return constants, workspace_kwargs

    def export(self, fpath):
        """
        routine to export tray data to save file. used to keep track of experimental conditions in certain tray.
        """
        return None
