import os
import json
from natsort import natsorted
import numpy as np
import matplotlib.pyplot as plt

MODULE_DIR = os.path.dirname(__file__)
LL_VERSIONS_DIR = os.path.join(MODULE_DIR, "versions", "liquidlabware")
AVAILABLE_VERSIONS = {
    os.path.splitext(f)[0]: os.path.join(LL_VERSIONS_DIR, f)
    for f in os.listdir(LL_VERSIONS_DIR)
    if ".json" in f
}


def available_versions(self):
    return AVAILABLE_VERSIONS


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
        self.volume = constants["wells"][self._openwells[0]][
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
        self._openwells = list(self._coordinates.keys())
        self._openwells = natsorted(
            self._openwells
        )  # should already be sorted, but just in case

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
            well = self._openwells.pop(0)  # take the next open slot
            self.contents[well] = contents
            self._openwells = natsorted(self._openwells)
            return well
        except IndexError as e:
            raise IndexError("This labware is full!")

    def unload(self, well: str):
        """Unload contents from a slot in the labware.
            Sorts the list of open slots so we always fill the lowest index open slot.

        Args:
            slot (str): which slot to unload

        Raises:
            ValueError: If that slot is already empty
        """
        if well not in self._coordinates:
            raise ValueError(f"{well} is not a valid well!")
        if well in self._openwells:
            raise ValueError(f"Cannot unload {well}, it's already empty!")
        self._openwells.append(well)
        self._openwells = natsorted(self._openwells)
        return self.contents.pop(well)

    def __repr__(self):
        out = f"<LiquidLabware> {self.name}, {self.volume/1e3} mL volume, {self.capacity} wells"
        return out

    def unload_all(self):
        """
        resets the labware to an empty state
        """
        self._openwells = list(self._coordinates.keys())
        self._openwells.sort()
        self.contents = {}

    def plot(self, solution_details=None, ax=None):
        """
        plot labware w/ solution occupants
        """
        if solution_details is None:
            label_solution_info = False
            solution_details = {}
        else:
            label_solution_info = True

        if ax is None:
            fig, ax = plt.subplots()

        xvals = np.unique([x for x, _, _ in self._coordinates.values()])
        yvals = np.unique([y for _, y, _ in self._coordinates.values()])
        markersize = 15

        for k, (x, y, z) in self._coordinates.items():
            if k in self.contents:
                solution = self.contents[k]
                label = str(solution)
                fillstyle = "full"
                if label_solution_info:
                    volume = solution_details.get(solution, {}).get(
                        "initial_volume_required", 0
                    )
                    if volume == 0:
                        label = "Empty well for " + label
                        fillstyle = "none"
                    else:
                        label = f"{volume} uL " + label

                ax.plot(
                    x,
                    y,
                    label=label,
                    marker="o",
                    linestyle="none",
                    markersize=markersize,
                    fillstyle=fillstyle,
                )
            else:
                ax.scatter(x, y, c="gray", marker="x", alpha=0.2)

        plt.sca(ax)
        ax.set_aspect("equal")
        plt.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.0)
        plt.title(self.name)
        plt.yticks(
            yvals[::-1],
            [chr(65 + i) for i in range(len(yvals))],
        )
        plt.xticks(xvals, [i + 1 for i in range(len(xvals))])
