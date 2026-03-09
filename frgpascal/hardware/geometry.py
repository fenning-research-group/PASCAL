import numpy as np
from natsort import natsorted
import os
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D

### https://stackoverflow.com/questions/15457786/ctrl-c-crashes-python-after-importing-scipy-stats
os.environ["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = (
    "1"  # to preserve ctrl-c with scipy loaded
)

from scipy.interpolate import LinearNDInterpolator
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper
import yaml

MODULE_DIR = os.path.dirname(__file__)
CALIBRATION_DIR = os.path.join(MODULE_DIR, "calibrations")
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class CoordinateMapper:
    """
    Transforms from one coordinate system (source) to another (destination).

    This class calculates the spatial offset between a set of measured source points 
    and ideal destination points. It projects the xy plane with a z-offset to map 
    coordinates accurately. 

    Notes
    -----
    Assumes the two coordinate systems are nearly parallel. It can handle some 
    slight rotation, but otherwise primarily performs translation in xy. Because 
    it projects the xy plane with a z-offset, this mapping approach will have 
    accuracy issues under severe rotation.

    Parameters
    ----------
    p0 : array_like
        The array of measured source coordinates `[[x, y, z], ...]`.
    p1 : array_like
        The array of ideal destination coordinates `[[x, y, z], ...]`
    """
    def __init__(self, p0, p1):
        self.destination = np.asarray(p1)
        self.source = np.asarray(p0)
        self.xyoffset = self.destination.mean(axis=0) - self.source.mean(axis=0)
        self.xyoffset[2] = 0  # no z offset, but keep in 3d
        self.zinterp = LinearNDInterpolator(self.destination[:, :2], self.source[:, 2])

    def map(self, p):
        """
        Map a specific point from the source coordinate frame to the destination frame.

        Parameters
        ----------
        p : array_like
            The point to transform. Can be a 2D `[x, y]` or 3D `[x, y, z]` coordinate.

        Returns
        -------
        ndarray
            The transformed 3D coordinate `[x, y, z]`.
        """
        if len(p) == 2:
            p = list(p)
            p.append(0)
        p = np.asarray(p, dtype=float)
        p[2] = self.zinterp(p[:2])
        pmap = p - self.xyoffset

        return pmap

def map_coordinates(name, slots, points, gantry: Gantry, z_clearance=5):
    """
    Prompts user to move gripper to target points on labware for calibration purposes.

    Parameters
    ----------
    name : str
        name of labware to save in filename of output calibrations yaml file
    slots : list
        str labels of the target points of interest, e.g. ['I1', 'A1', 'A5', 'I5']
    points : list
        the vertex points [[x,y,z], [x1,y1,z1], ...] to be measured. These points will be used by 
        `frgpascal.hardware.geometry.CoordinateMapper` to define the the xy coordinate map of a given labware.
    gantry : `frgpascal.hardware.gantry.Gantry`
        The gantry hardware used to move the grippers along the X, Y, Z axes.
    z_clearance : int, optional
        Vertical offset (mm) from points to start at to prevent collision by initial misalignment, defaults to 5.

    Returns
    -------
    `frgpascal.hardware.geometry.CoordinateMapper`
        Instance of CoordinateMapper, initializes with the measured coordinates of the vertex points in absolute (`p0`)
        and relative (`p1`) frames of reference. For the relative (`p1`) frame of reference, we define with respect to the
        first vertex point element provided in points
    """
    points = np.asarray(points).astype(float).round(2)  # destination coordinates
    p_prev = points[0]

    points_source_guess = points

    points_source_meas = []  # source coordinates
    for slotname, p in zip(slots, points_source_guess):
        movedelta = p - p_prev  # offset between current and next point
        gantry.moverel(*movedelta, zhop=True) # move to next point but don't crash into samples.
        # gantry.moverel(*movedelta, zhop=False)  # move to next point
        print(f"Move to {slotname}")
        gantry.gui()  # prompt user to align gantry to exact target location
        points_source_meas.append(gantry.position)
        gantry.moverel(z=z_clearance, zhop=False)
        p_prev = p

    # save calibration
    with open(os.path.join(CALIBRATION_DIR, f"{name}_calibration.yaml"), "w") as f:
        out = {
            "p0": points_source_meas,
            "p1": np.asarray(points)
            .astype(float)
            .round(2)
            .tolist(),  # rounding error bs
        }
        yaml.dump(out, f)

    return CoordinateMapper(p0=points_source_meas, p1=points)


class Workspace:
    """
    General class for defining planar workspaces. Primary use is to calibrate the coordinate system of this workspace to
    the reference workspace to account for any tilt/rotation/translation in workspace mounting.

    Parameters
    ----------
    name : str
        name of workspaces, for logging purposes.
    pitch : tuple
        Space between neighboring slots (x,y) (mm). Assumes workspace is 2D, parallel to `frgpascal.hardware.gantry.Gantry` XY plane.
    gridsize : tuple
        Number of slots available (x,y)
    gantry : `frgpascal.hardware.gantry.Gantry`
        Gantry control object, needed for calibration.
    gripper : `frgpascal.hardware.gripper.Gripper`
        Gripper control object, needed for calibration.
    p0 : list, optional
        approximate location of the lower left slot of the labware, for calibration initial point.
    testslots : list, optional
        Slots with which to calibrate the plane tilt from. Defaults to None.
    z_clearance : float, optional
        Vertical clearance (mm) to give when calibrating points, to avoid crashes. Defaults to 5.
    openwidth : float, optional
        Width (mm) to open gripper to when picking samples from this workspace. Defaults to 20.
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
        openwidth: float = 12,
    ):
        print("Initializing Workspace")
        self.__calibrated = False  # set to True after calibration routine has been run
        self.name = name
        if gantry is None and gripper is None:
            self.__is_simulation = True
            self.p0 = np.array([0, 0, 0])
        else:
            self.__is_simulation = False
            self.p0 = np.asarray(p0) + [0, 0, 5]
        self.gantry = gantry
        self.gripper = gripper
        # coordinate system properties
        self.pitch = pitch
        self.gridsize = gridsize
        self.capacity = gridsize[0] * gridsize[1]
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
        """
        Internal method to build the theoretical coordinate dictionary mapping 
        slot names (e.g., 'A1') to their physical offsets based on pitch and gridsize.
        """
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
        """
        Get the calibrated physical 3D coordinates for a specific slot name.

        Parameters
        ----------
        name : str
            The name of the slot (e.g., 'A1').

        Returns
        -------
        ndarray
            The calibrated `[x, y, z]` coordinate of the requested slot.

        Raises
        ------
        Exception
            If the workspace has not yet been calibrated.
        Exception
            If the transformed coordinate results in `np.nan` due to a bad calibration mapping.
        """
        if self.__calibrated == False:
            raise Exception(f"Need to calibrate {self.name} before use!")
        coords = self.transform.map(self._coordinates[name])
        if any(np.isnan(coords)):
            raise Exception(
                "Coordinate was transformed into nan! Check for rounding errors on calibration .yamls"
            )
        return self.transform.map(self._coordinates[name])

    def __call__(self, name):
        """
        Alias for `slot_coordinates`, allows calling the workspace object directly 
        with a slot name to get its coordinates.

        Parameters
        ----------
        name : str
            The name of the slot.

        Returns
        -------
        ndarray
            The calibrated `[x, y, z]` coordinate.
        """
        return self.slot_coordinates(name)

    def calibrate(self):
        """
        Initiate the physical calibration sequence using the gantry GUI.

        This method moves the gantry to the defined test slots (usually the corners) 
        and allows the user to manually align the gripper. It then calculates the 
        coordinate transformation matrix for the entire workspace.

        Raises
        ------
        Exception
            If the workspace was initialized in simulation mode without a real gantry.
        """
        if self.__is_simulation:
            raise Exception("Cannot calibrate a simulated workspace")
        self.gantry.moveto(*self.p0)
        self.gripper.GRIPPERTIMEOUT = (
            69420  # prevents the gripper from closing during calibration of sampletray
        )
        self.gripper.open(self.OPENWIDTH)
        self.transform = map_coordinates(
            self.name,
            self.testslots,
            self.testpoints,
            self.gantry,
            self.z_clearance,
        )
        self.__calibrated = True
        self.GRIPPERTIMEOUT = constants["gripper"][
            "idle_timeout"
        ]  # reset to the hardware constants value

    # def _save_calibration(self):
    #     if not self.__calibrated:
    #         raise ValueError(
    #             "Need to calibrate before you can save a calibration, dingus!"
    #         )

    def _load_calibration(self):
        """
        Load a previously saved coordinate calibration mapping from the local YAML file
        """
        with open(
            os.path.join(CALIBRATION_DIR, f"{self.name}_calibration.yaml"), "r"
        ) as f:
            pts = yaml.load(f, Loader=yaml.FullLoader)
        self.transform = CoordinateMapper(p0=pts["p0"], p1=pts["p1"])
        self.__calibrated = True

    def load(self, contents) -> str:
        """
        Load new contents into the workspace labware.

        Automatically finds the next available open slot and assigns the contents to it.

        Parameters
        ----------
        contents : object
            A `SolutionRecipe`, sample object, or string representing the solution

        Returns
        -------
        str
            The name of the slot that has been allocated to the new contents.

        Raises
        ------
        IndexError
            If all slots in the labware are currently occupied.
        """
        try:
            slot = self._openslots.pop(0)  # take the next open slot
            self.contents[slot] = contents
            return slot
        except IndexError as e:
            raise IndexError("This labware is full!")

    def unload(self, slot: str):
        """
        Unload contents from a specific slot in the labware.
        
        This also re-sorts the list of open slots so the workspace consistently 
        fills the lowest index open slot on subsequent loads.

        Parameters
        ----------
        slot : str
            The name of the slot to unload (e.g., 'A1').

        Returns
        -------
        object
            The contents that were removed from the specified slot.

        Raises
        ------
        ValueError
            If the requested slot does not exist within the workspace grid.
        ValueError
            If the requested slot is already empty.
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
        Reset the workspace to a completely empty state.
        """
        self._openslots = list(self._coordinates.keys())
        self._openslots.sort()
        self.contents = {}

    def plot(tray, ax=None, is_samples = False, updated_colorscheme = False):
        """
        (deprecated?) Plot the current spatial layout and contents of the labware.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            A pre-existing matplotlib axis to plot on. If None, a new figure is created.
        is_samples : bool, optional
            Flag to indicate if the plot should use sample-specific coloring schemes. Defaults to False.
        updated_colorscheme : bool, optional
            Flag to use the newer, more distinguishable color mapping. Defaults to False.
        """
        if ax is None:
            fig, ax = plt.subplots()
            ax.set_aspect("equal")

        plt.sca(ax)
        xvals = np.unique([x for x, _, _ in tray._coordinates.values()])
        yvals = np.unique([y for _, y, _ in tray._coordinates.values()])
        markersize = 30

        unique_substrates = {}
        empty_slots = {"x": [], "y": []}
        for k, (x, y, z) in tray._coordinates.items():
            if k in tray.contents:
                substrate = tray.contents[k].substrate
                if substrate not in unique_substrates:
                    unique_substrates[substrate] = {"x": [], "y": []}
                unique_substrates[substrate]["x"].append(x)
                unique_substrates[substrate]["y"].append(y)
            else:
                empty_slots["x"].append(x)
                empty_slots["y"].append(y)


        if updated_colorscheme:
            if is_samples: # sample trays
                cmap_x = plt.get_cmap('tab10', len(xvals))
                cmap_y = plt.get_cmap('plasma', len(yvals))
                cmap_2 = plt.get_cmap('PuBuGn', len(yvals))
                markers = ['o', 's', 'p', 'D', 'h', 'H']
            if not is_samples: # liquid labware trays
                cmap_x = plt.get_cmap('plasma', len(xvals)) 
                cmap_y = plt.get_cmap('tab10', len(yvals))
                markers = ['o', 's', 'D', 'p', 'h', 'H']
            norm_x = Normalize(vmin = min(xvals), vmax = max(xvals))
            norm_y = Normalize(vmin = min(yvals), vmax = max(yvals))

            markers_dict = {}
            if is_samples:
                for j, x in enumerate(xvals):
                    if j >= len(markers):
                        j = j - len(markers)
                    markers_dict[x] = markers[j]
                gamma = 0
                scatters = []
                labels = []
                for label, c in unique_substrates.items():
                    for c_x, c_y in zip(c["x"], c["y"]):
                        marker_0 = markers_dict[c_x]
                        if gamma%2:
                            facecolor_0 = cmap_2(norm_y(c_y))
                        else:
                            facecolor_0 = cmap_y(norm_y(c_y))
                        gamma += 1

                        sc = plt.scatter(c_x, c_y, label = label, marker = marker_0, facecolor = facecolor_0, edgecolor = 'black', s = 150)
                        scatters.append(sc)
                        labels.append(label)
                    # plt.scatter(c["x"], c["y"], label=label, marker=markers[c["x"]], facecolor = cmap_y(norm_y(c["y"])))
            if not is_samples:
                for j, y in enumerate(yvals):
                    if j >= len(markers):
                        j = j - len(markers)
                    markers_dict[y] = markers[j]
                for label, c in unique_substrates.items():

                    plt.scatter(c["x"], c["y"], label=label, marker=markers[c["y"]], facecolor = cmap_x(norm_x(c["x"])))
        if not updated_colorscheme:
            for label, c in unique_substrates.items():
                plt.scatter(c["x"], c["y"], label=label, marker="s")
        plt.scatter(empty_slots["x"], empty_slots["y"], c="gray", marker="x", alpha=0.2)
        if updated_colorscheme:
            plt.legend(scatters, labels, ncol = 5, bbox_to_anchor = (1.05, 1), loc = 2, borderaxespad = 0.0)
            # plt.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.0, ncol = 5)
        if not updated_colorscheme:
            plt.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.0)
        plt.title(tray.name)
        plt.yticks(
            yvals[::-1],
            [chr(65 + i) for i in range(len(yvals))],
        )
        plt.xticks(xvals, [i + 1 for i in range(len(xvals))])

    def plot_new(tray, ax=None, is_samples = False):
        """
        An updated plotting method to visualize the contents of the labware tray.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            A pre-existing matplotlib axis to plot on. If None, a new figure is created.
        is_samples : bool, optional
            Flag to apply sample-specific discrete colormaps and markers. Defaults to False.
        """
        if ax is None:
            fig, ax = plt.subplots()
            ax.set_aspect("equal")

        plt.sca(ax)
        xvals = np.unique([x for x, _, _ in tray._coordinates.values()])
        xvals = natsorted(xvals)
        # print(xvals)
        yvals = np.unique([y for _, y, _ in tray._coordinates.values()])
        yvals = natsorted(yvals)
        markersize = 30

        unique_substrates = {}
        empty_slots = {"x": [], "y": []}
        for k, (x, y, z) in tray._coordinates.items():
            if k in tray.contents:
                substrate = tray.contents[k].substrate
                if substrate not in unique_substrates:
                    unique_substrates[substrate] = {"x": [], "y": []}
                unique_substrates[substrate]["x"].append(x)
                unique_substrates[substrate]["y"].append(y)
            else:
                empty_slots["x"].append(x)
                empty_slots["y"].append(y)

        if is_samples: # sample trays
            cmap_x = plt.get_cmap('tab10', len(xvals))
            cmap_y = plt.get_cmap('plasma', len(yvals))
            cmap_2 = plt.get_cmap('PuBuGn', len(yvals))
            markers = ['o', 's', 'D', 'P', 'X', 'H']
        if not is_samples: # liquid labware trays
            cmap_x = plt.get_cmap('plasma', len(xvals)) 
            cmap_y = plt.get_cmap('tab10', len(yvals))
            markers = ['o', 's', 'D', 'P', 'X', 'H']
        norm_x = Normalize(vmin = min(xvals), vmax = max(xvals))
        norm_y = Normalize(vmin = min(yvals), vmax = max(yvals))
        # print(yvals)
        # print(xvals)
        colors_grid = {}
        for y in yvals:
            if np.where(yvals == y)[0][0]%2:
                color_opt = cmap_y(norm_y(y))
            else:
                color_opt = cmap_2(norm_y(y))
            colors_grid[y] = color_opt

        markers_dict = {}
        if is_samples:
            for j, x in enumerate(xvals):
                if j >= len(markers):
                    j = j - len(markers)
                markers_dict[x] = markers[j]
            gamma = 0
            x_coordinates = []
            y_coordinates = []
            colors = []
            markertypes = []
            scatters = []
            labels = []
            for label, c in unique_substrates.items():
                for c_x, c_y in zip(c["x"], c["y"]):
                    marker_0 = markers_dict[c_x]
                    # if gamma%2 == 0:
                    #     facecolor_0 = cmap_2(norm_y(c_y))
                    # else:
                    #     facecolor_0 = cmap_y(norm_y(c_y))

                    # gamma += 1
                    facecolor_0 = colors_grid[c_y]
                    sc = plt.scatter(c_x, c_y, label = label, marker = marker_0, facecolor = facecolor_0, edgecolor = 'black', s = 150)
                    x_coordinates.append(c_x)
                    y_coordinates.append(c_y)
                    colors.append(facecolor_0)
                    markertypes.append(marker_0)
                    scatters.append(sc)
                    labels.append(label)
                # plt.scatter(c["x"], c["y"], label=label, marker=markers[c["x"]], facecolor = cmap_y(norm_y(c["y"])))
        if not is_samples:
            for j, y in enumerate(yvals):
                if j >= len(markers):
                    j = j - len(markers)
                markers_dict[y] = markers[j]
            for label, c in unique_substrates.items():
                plt.scatter(c["x"], c["y"], label=label, marker=markers[c["y"]], facecolor = cmap_x(norm_x(c["x"])))
        
        ncols = len(xvals)
        nrows = len(yvals)
        grid = [[None for _ in range(ncols)] for _ in range(nrows)]
        color_grid = [[None for _ in range(ncols)] for _ in range(nrows)]
        marker_grid = [[None for _ in range(ncols)] for _ in range(nrows)]
        for xi, yi, label, c, m in zip(x_coordinates, y_coordinates, labels, colors, markertypes):
            # print(xi)
            # col_idx = np.where(xvals == xi)[0][0]
            # row_idx = np.where(yvals == yi)[0][0]
            col_idx = xvals.index(xi)
            row_idx = yvals.index(yi)
            grid[row_idx][col_idx] = label
            color_grid[row_idx][col_idx] = c
            marker_grid[row_idx][col_idx] = m
        
        plt.scatter(empty_slots["x"], empty_slots["y"], c="gray", marker="x", alpha=0.2)
        handles = []
        legend_labels = []
        for c in range(ncols):
            for r in reversed(range(nrows)):
                label = grid[r][c]
                color = color_grid[r][c]
                marker = marker_grid[r][c]
                if label is None:
                    handles.append(Line2D([0], [0], marker='x', linestyle = 'None'))
                    legend_labels.append("")
                else:
                    handles.append(Line2D([0], [0], marker = marker, linestyle = 'None', markersize = 8, color = color, markerfacecolor = color, markeredgecolor = 'black'))
                    legend_labels.append(label)

        ax.legend(handles, legend_labels, ncol = ncols,
                  bbox_to_anchor = (1.05, 1), frameon = True, handletextpad = 0.4, labelspacing = 0.6)

        # plt.scatter(empty_slots["x"], empty_slots["y"], c="gray", marker="x", alpha=0.2)
        # plt.legend(scatters, labels, ncol = 5, bbox_to_anchor = (1.05, 1), loc = 2, borderaxespad = 0.0)
            # plt.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.0, ncol = 5)
        plt.title(tray.name)
        plt.yticks(
            yvals[::-1],
            [chr(65 + i) for i in range(len(yvals))],
        )
        plt.xticks(xvals, [i + 1 for i in range(len(xvals))])

