import os
import yaml
from frgpascal.hardware.geometry import Workspace
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper

MODULE_DIR = os.path.dirname(__file__)
TRAY_VERSIONS_DIR = os.path.join(MODULE_DIR, "versions", "sampletrays")
AVAILABLE_VERSIONS = {
    os.path.splitext(f)[0]: os.path.join(TRAY_VERSIONS_DIR, f)
    for f in os.listdir(TRAY_VERSIONS_DIR)
    if ".yaml" in f
}


def available_versions(self):
    return AVAILABLE_VERSIONS


class SampleTray(Workspace):
    def __init__(
        self, name, version, gantry: Gantry, gripper: Gripper, p0=[None, None, None],
    ):
        constants, workspace_kwargs = self._load_version(version)
        super().__init__(
            name=name, gantry=gantry, gripper=gripper, p0=p0, **workspace_kwargs
        )

        # only consider slots with blanks loaded
        self.contents = {}

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
        return constants, workspace_kwargs

    def export(self, fpath):
        """
        routine to export tray data to save file. used to keep track of experimental conditions in certain tray.
        """
        return None
