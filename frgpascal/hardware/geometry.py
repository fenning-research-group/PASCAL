import numpy as np
import os

### https://stackoverflow.com/questions/15457786/ctrl-c-crashes-python-after-importing-scipy-stats
os.environ[
    "FOR_DISABLE_CONSOLE_CTRL_HANDLER"
] = "1"  # to preserve ctrl-c with scipy loaded

from scipy.interpolate import LinearNDInterpolator
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper
import yaml

MODULE_DIR = os.path.dirname(__file__)
CALIBRATION_DIR = os.path.join(MODULE_DIR, "calibrations")


class CoordinateMapper:
    """Transforms from one coordinate system (source) to another (destination)
    Assumes the two coordinate systems are nearly parallel - can handle some rotation,
    but otherwise just does translation in xy. Actually projects xy plane with z offset,
    so this will have issues under severe rotation.
    """

    def __init__(self, p0, p1):
        self.destination = np.asarray(p1)
        self.source = np.asarray(p0)
        self.xyoffset = self.destination.mean(axis=0) - self.source.mean(axis=0)
        self.xyoffset[2] = 0  # no z offset, but keep in 3d
        self.zinterp = LinearNDInterpolator(self.destination[:, :2], self.source[:, 2])

    def map(self, p):
        if len(p) == 2:
            p = list(p)
            p.append(0)
        p = np.asarray(p)
        p[2] = self.zinterp(p[:2])
        pmap = p - self.xyoffset

        # z interpolated to nan if all z points are 0 during calibration. nice tramming!
        # if np.isnan(pmap[2]):
        #     pmap[2] = 0
        return pmap


def map_coordinates(name, slots, points, gantry: Gantry, z_clearance=5):
    """prompts user to move gripper to target points on labware for
    calibration purposes


    :param points: list of points [[x,y,z],[x,y,z]...] to map to. In destination coordinates
    :type points: list
    :param p0: coordinate of first point in points, in source coordinates
    :type p0: list
    :param gantry: gantry object
    :type gantry: gantry.Gantry
    :param z_clearance: verstical offset (mm) from points to start at to prevent collision by initial misalignment, defaults to 5
    :type z_clearance: int, optional
    """

    points = np.asarray(points).round(2)  # destination coordinates
    p_prev = points[0]

    points_source_guess = points

    points_source_meas = []  # source coordinates
    for slotname, p in zip(slots, points_source_guess):
        movedelta = p - p_prev  # offset between current and next point
        gantry.moverel(*movedelta, zhop=False)  # move to next point
        print(f"Move to {slotname}")
        gantry.gui()  # prompt user to align gantry to exact target location
        points_source_meas.append(gantry.position)
        gantry.moverel(z=z_clearance, zhop=False)
        p_prev = p

    # save calibration
    with open(os.path.join(CALIBRATION_DIR, f"{name}_calibration.yaml"), "w") as f:
        out = {"p0": points_source_meas, "p1": points.tolist()}
        yaml.dump(out, f)

    return CoordinateMapper(p0=points_source_meas, p1=points)


class Workspace:
    """
    General class for defining planar workspaces. Primary use is to calibrate the coordinate system of this workspace to
    the reference workspace to account for any tilt/rotation/translation in workspace mounting.
    """

    def __init__(
        self,
        name: str,
        pitch: tuple,
        gridsize: tuple,
        gantry: Gantry = None,
        gripper: Gripper = None,
        p0=[0, 0, 0],
        testslots=None,
        z_clearance: float = 5,
        openwidth: float = 14,
    ):
        """
        Args:
            name (str): Name of workspaces, for logging purposes
            pitch (tuple): space between neighboring slots (x,y) (mm). Assumes workspace is 2D, parallel to gantry XY plane
            gridsize (tuple): number of slots available (x,y)
            gantry (Gantry): Gantry control object. needed for calibration
            p0 (list, optional): [description]. approximate location of lower left slot, for calibration initial point.
            testslots ([type], optional. Slots to calibrate the plane tilt from. Defaults to None.
            z_clearance (float, optional): vertical clearance (mm)to give when calibrating points, to avoid crashes. Defaults to 5.
            openwidth (float, optional): width (mm) to open gripper to when picking samples from this workspace. Defaults to 20.

        Raises:
            Exception: [description]
        """
        # :param name: name of workspace. For logging purposes
        # :type name: string
        # :param p0: Approximate location of lower left slot in the source (gantry) coordinate system
        # :type name: list [x,y,z]
        # :param pitch: space between neighboring breadboard holes, mm, (x,y). assume constrained in xy plane @ z = 0
        # :type pitch: [type]
        # :param gridsize: number of grid points available, (x,y)
        # :type gridsize: [type]
        # :param gantry: Gantry control object
        # :type gridsize: gantry.Gantry
        # :param testslots: slots to probe during calibration, defaults to None
        # :type testslots: [type], optional
        # :param z_clearance: vertical offset when calibrating points, in mm. ensures no crashing before calibration, defaults to 5
        # :type z_clearance: int, optional

        self.__calibrated = False  # set to True after calibration routine has been run
        self.name = name
        if gantry is None and gripper is None:
            self.__is_simulation = True
        else:
            self.__is_simulation = False
        self.gantry = gantry
        self.gripper = gripper
        # coordinate system properties
        self.pitch = pitch
        self.p0 = np.asarray(p0) + [0, 0, 5]
        self.gridsize = gridsize
        self.z_clearance = z_clearance
        self.OPENWIDTH = openwidth
        self.__generate_coordinates()

        if testslots is None:
            testslots = []
            testslots.append(
                f"{self._ycoords[0]}{self._xcoords[0]}"
            )  # bottom left corner
            testslots.append(
                f"{self._ycoords[-1]}{self._xcoords[0]}"
            )  # top left corner
            testslots.append(
                f"{self._ycoords[-1]}{self._xcoords[-1]}"
            )  # top right corner
            testslots.append(
                f"{self._ycoords[0]}{self._xcoords[-1]}"
            )  # bottom right corner
        # elif len(testslots) != 4:
        #     raise Exception(
        #         'Must provide four corner test points, in list form ["A1", "A2", "B3", "B4"], etc'
        #     )

        self.testslots = testslots
        self.testpoints = np.array(
            [self._coordinates[name] for name in testslots]
        ).astype(np.float32)

    def __generate_coordinates(self):
        def letter(num):
            # converts number (0-25) to letter (A-Z)
            return chr(ord("A") + num)

        self._coordinates = {}
        self._openslots = []
        self._ycoords = [
            letter(self.gridsize[1] - yidx - 1) for yidx in range(self.gridsize[1])
        ]  # lettering +y -> -y = A -> Z
        self._xcoords = [
            xidx + 1 for xidx in range(self.gridsize[0])
        ]  # numbering -x -> +x = 1 -> 100

        for yidx in range(self.gridsize[1]):  # y
            for xidx in range(self.gridsize[0]):  # x
                name = f"{self._ycoords[yidx]}{self._xcoords[xidx]}"
                self._coordinates[name] = [
                    xidx * self.pitch[0],
                    yidx * self.pitch[1],
                    0,
                ]
                self._openslots.append(name)
                self._openslots.sort()
                # self._coordinates[name] = [p + poffset for p, poffset in zip(relative_position, self.offset)]

    def slot_coordinates(self, name):
        if self.__calibrated == False:
            raise Exception(f"Need to calibrate {self.name} before use!")
        return self.transform.map(self._coordinates[name])

    def __call__(self, name):
        return self.slot_coordinates(name)

    def calibrate(self):
        if self.__is_simulation:
            raise Exception("Cannot calibrate a simulated workspace")
        self.gantry.moveto(*self.p0)
        self.gripper.open(self.OPENWIDTH)
        self.transform = map_coordinates(
            self.name,
            self.testslots,
            self.testpoints,
            self.gantry,
            self.z_clearance,
        )
        self.__calibrated = True

    # def _save_calibration(self):
    #     if not self.__calibrated:
    #         raise ValueError(
    #             "Need to calibrate before you can save a calibration, dingus!"
    #         )

    def _load_calibration(self):
        with open(
            os.path.join(CALIBRATION_DIR, f"{self.name}_calibration.yaml"), "r"
        ) as f:
            pts = yaml.load(f, Loader=yaml.FullLoader)
        self.transform = CoordinateMapper(p0=pts["p0"], p1=pts["p1"])
        self.__calibrated = True

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
            ValueError: If that slot either does not exist, or is already empty
        """
        if slot not in self._coordinates:
            raise ValueError(f"{slot} is not a valid slot")
        if slot in self._openslots:
            raise ValueError(f"Cannot unload {slot}, it's already empty!")
        self._openslots.append(slot)
        self._openslots.sort()
        return self.contents.pop(slot)  # remove the slot from the contents dictionary

    def unload_all(self):
        """
        resets the labware to an empty state
        """
        self._openslots = list(self._coordinates.keys())
        self._openslots.sort()
        self.contents = {}
