import os
import json

MODULE_DIR = os.path.dirname(__file__)
LL_VERSIONS_DIR = os.path.join(MODULE_DIR, "versions", "liquidlabware")
AVAILABLE_VERSIONS = {
    os.path.splitext(f)[0]: os.path.join(LL_VERSIONS_DIR, f)
    for f in os.listdir(LL_VERSIONS_DIR)
}


class LiquidLabware:
    def __init__(self, name: str, version: str):
        if "-" in name:
            raise ValueError(' "-" character not allowed in LiquidLabware name')
        constants = self._load_version(version)
        self.name = name
        numx = len(constants["ordering"])
        numy = len(constants["ordering"][0])
        self.shape = (numy, numx)  # grid dimensions
        self.capacity = numy * numx  # number of slots
        self.volume = constants["wells"][self._openslots[0]][
            "totalLiquidVolume"
        ]  # in uL. assumes all wells have same volume!
        self.contents = {}

    def _load_version(self, version):
        """Loads the version file for the labware. 
        This should be the same json file used to define custom labware for opentrons.
        Also extracts coordinates from the json file.
        """
        if version not in AVAILABLE_VERSIONS:
            raise Exception(
                f'Invalid liquid labware version "{version}".\n Available versions are: {list(AVAILABLE_VERSIONS.keys())}.'
            )
        with open(AVAILABLE_VERSIONS[version], "r") as f:
            constants = json.load(f)

        self._coordinates = {
            k: (v["x"], v["y"], v["z"]) for k, v in constants["wells"].items()
        }
        self._openslots = list(self._coordinates.keys())
        self._openslots.sort()  # should already be sorted, but just in case

        return constants

    def load(self, contents) -> str:
        """Load new contents into the labware. Returns the next empty slot, or error if none exists.

        Args:
            contents (object): SolutionRecipe or a string representing the solution

        Raises:
            IndexError: If the labware is full  

        Returns:
            (str): which slot has been allocated to the new contents
        """
        try:
            slot = self._openslots.pop(0)  # take the next open slot
            self.contents[slot] = contents
            return slot
        except IndexError as e:
            raise IndexError("This labware is full!")

    def unload(self, slot: str):
        """Unload contents from a slot in the labware. 
            Sorts the list of open slots so we always fill the lowest index open slot. 

        Args:
            slot (str): which slot to unload

        Raises:
            ValueError: If that slot is already empty
        """
        if slot not in self._coordinates:
            raise ValueError(f"{slot} is not a valid slot")
        if slot in self._openslots:
            raise ValueError(f"Cannot unload {slot}, it's already empty!")
        self._openslots.append(slot)
        self._openslots.sort()
        return self.condents.pop(slot)

    def __repr__(self):
        out = f"<LiquidLabware> {self.name}, {self.volume/1e3} mL volume, {self.capacity} wells"
        return out

    def unload_all(self):
        """
        resets the labware to an empty state
        """
        self._openslots = list(self._coordinates.keys())
        self._openslots.sort()
        self.contents = {}
