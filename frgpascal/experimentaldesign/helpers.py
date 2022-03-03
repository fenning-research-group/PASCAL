import numpy as np
import json
import csv
import itertools
from frgpascal.experimentaldesign.tasks import (
    Solution,
    Sample,
    Spincoat,
    Drop,
    Anneal,
    Rest,
)
from copy import deepcopy
import uuid
import matplotlib.pyplot as plt
import pandas as pd
from frgpascal.system import generate_workers, build
from frgpascal.workers import Worker_Hotplate
from frgpascal.experimentaldesign.protocolwriter import generate_ot2_protocol
from typing import Tuple
import mixsol as mx
from mixsol.mix import _solutions_to_matrix
import random

WORKERS = generate_workers()
HOTPLATE_NAMES = [
    name for name, worker in WORKERS.items() if isinstance(worker, Worker_Hotplate)
]

#### General
def generate_unique_id():
    return str(uuid.uuid4())


#### name parsing helper functions
def components_to_name(components, delimiter="_"):
    composition_label = ""
    for c, n in components.items():
        if n > 0:
            composition_label += "{0}{1:.2f}{2}".format(c, n, delimiter)

    return composition_label[:-1]


def name_to_components(
    name,
    factor=1,
    delimiter="_",
):
    """
    given a chemical formula, returns dictionary with individual components/amounts
    expected name format = 'MA0.5_FA0.5_Pb1_I2_Br1'.
    would return dictionary with keys ['MA, FA', 'Pb', 'I', 'Br'] and values [0.5,.05,1,2,1]*factor
    """
    components = {}
    for part in name.split(delimiter):
        species = part
        count = 1.0
        for l in range(len(part), 0, -1):
            try:
                count = float(part[-l:])
                species = part[:-l]
                break
            except:
                pass
        if species == "":
            continue
        components[species] = count * factor
    return components


#### stock solution management


def where_to_store(volume, options):
    for ll in options:
        if volume <= ll.volume and len(ll._openwells) > 0:
            return ll
    raise ValueError(f"No options have enough space to hold {volume/1e3:.2f} mL!")


def interpolate_solutions(solutions: list, steps: int) -> list:
    """Generate a list of solutions that are a linear interpolation between the given solutions

    Args:
        solutions (list): List of Solution objects to be interpolated between
        steps (int): number of steps to interpolate between endpoint solutions. 1 will return the original list, 2 will split into 50% increments, 3 split into 33% increments, etc.

    Returns:
        list: list of unique Solution objects resulting from the interpolation
    """

    solution_matrix, solvent_idx, components = _solutions_to_matrix(solutions)
    solvent_components = [components[i] for i in solvent_idx]
    solution_idx = list(range(len(solutions)))
    tweened_solutions = []
    for solution_indices in itertools.combinations_with_replacement(
        solution_idx, steps
    ):
        svector = np.mean([solution_matrix[i] for i in solution_indices], axis=0)
        molarity = np.mean([solutions[i].molarity for i in solution_indices])
        solutes = components_to_name(
            {
                c: v / molarity
                for c, v in zip(components, svector)
                if v > 0 and c not in solvent_components
            }
        )
        solvent = components_to_name(
            {
                c: v
                for c, v in zip(components, svector)
                if v > 0 and c in solvent_components
            }
        )
        new_solution = Solution(solutes=solutes, solvent=solvent, molarity=molarity)
        if new_solution not in tweened_solutions:
            tweened_solutions.append(new_solution)

    return tweened_solutions


#### Plot contents of sample tray for loading guidance


def plot_tray(tray, ax=None):
    """
    plot tray w/ substrates to load prior to experiment start
    """
    if ax is None:
        fig, ax = plt.subplots()
        ax.set_aspect("equal")

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

    for label, c in unique_substrates.items():
        plt.scatter(c["x"], c["y"], label=label, marker="s")
    plt.scatter(empty_slots["x"], empty_slots["y"], c="gray", marker="x", alpha=0.2)

    plt.sca(ax)
    plt.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.0)
    plt.title(tray.name)
    plt.yticks(
        yvals[::-1],
        [chr(65 + i) for i in range(len(yvals))],
    )
    plt.xticks(xvals, [i + 1 for i in range(len(xvals))])


#### Construct sample list from experimental mesh


def apply_solution_mesh_to_drop(drop: Drop, solution_mesh):
    """
    given a drop, apply the solution mesh to the drop
    """
    if type(drop.solution) == Solution:
        return [drop]
    if drop.solution not in solution_mesh:
        raise Exception(f'Solution placeholder "{drop.solution}" not in solution mesh!')
    solutions = solution_mesh[drop.solution]
    all_drops = []
    base_drop = drop.to_dict()
    for s in solutions:
        base_drop["solution"] = s
        all_drops.append(Drop(**base_drop))
    return all_drops


def apply_solution_mesh(spincoat: Spincoat, solution_mesh):
    """
    given a spincoat, apply the solution mesh to the spincoat
    """
    drop_options = [
        apply_solution_mesh_to_drop(d, solution_mesh) for d in spincoat.drops
    ]
    spincoats = [
        Spincoat(
            steps=spincoat.steps,
            drops=ds,
        )
        for ds in itertools.product(*drop_options)
    ]
    return spincoats


def build_sample_list(
    input_substrates: list,
    steps: list,
    solution_mesh: dict = {},
    n_repeats: int = 1,
    starting_index: int = 0,
) -> list:
    """
    Permutes experimental mesh into sample list
    """
    sample_list = []
    listedsteps = []
    for step in steps:
        if type(step) != list:
            listedsteps.append([step])
        else:
            listedsteps.append(step)

    all_worklists = []
    for worklist in itertools.product(*listedsteps):
        this_set_of_steps = []
        for step in worklist:
            if step is None:
                continue
            if type(step) == Spincoat:
                this_set_of_steps.append(
                    apply_solution_mesh(deepcopy(step), solution_mesh)
                )
            else:
                this_set_of_steps.append([deepcopy(step)])
        all_worklists += list(itertools.product(*this_set_of_steps))

    idx = starting_index
    for wl in all_worklists:
        for sub in input_substrates:
            for r in range(n_repeats):
                name = f"sample{idx}"
                idx += 1
                this_sample = Sample(
                    name=name,
                    substrate=sub,
                    worklist=deepcopy(wl),
                    storage_slot=None
                    # sampleid=sampleid
                )
                sample_list.append(this_sample)
    return sample_list


def load_sample_trays(samples: list, available_trays: list):
    """Assign slots on the sample tray for all samples

    Args:
        samples (list): list of Sample objects to be loaded onto trays
        available_trays (list): list of SampleTray objects that can accept Samples
    """

    def get_storage_slot(name, current_tray, trays):
        loaded = False
        while not loaded:
            try:
                slot = current_tray.load(name)
                loaded = True
            except:
                try:
                    current_tray = next(trays)
                except StopIteration:
                    raise StopIteration(
                        "No more slots available in your storage trays!"
                    )
        return {"tray": current_tray.name, "slot": slot}, current_tray, trays

    for tray in available_trays:
        tray.unload_all()
    trays = iter(available_trays)
    current_tray = next(trays)
    for sample in samples:
        storage_slot, current_tray, trays = get_storage_slot(
            sample, current_tray, trays
        )
        sample.storage_slot = storage_slot
        for task in sample.worklist:
            if isinstance(task, Rest):
                task.workers = [WORKERS[storage_slot["tray"]]]


def samples_to_dataframe(samples):
    dfdata = []
    for sample in samples:
        this = {
            "name": sample.name,
            "storage_tray": sample.storage_slot["tray"],
            "storage_slot": sample.storage_slot["slot"],
            "substrate": sample.substrate,
            "worklist": json.dumps([task.to_dict() for task in sample.worklist]),
        }
        task_idx = {}
        for task in sample.worklist:
            if task.task not in task_idx:
                task_idx[task.task] = 0
            header = f"{task.task}{task_idx[task.task]}_"
            task_idx[task.task] += 1
            for c, v in task.to_dict().get("details", {}).items():
                if c == "drops":
                    for drop_idx, d in enumerate(v):
                        key = header + f"drop{drop_idx}_"
                        for aspect in ["time", "height", "rate", "volume"]:
                            this[key + aspect] = d[aspect]

                        this[key + "molarity"] = d["solution"]["molarity"]
                        this[key + "solutes"] = d["solution"]["solutes"]
                        this[key + "solutes_dict"] = json.dumps(
                            task.drops[drop_idx].solution.solute_dict
                        )

                        this[key + "solvent"] = d["solution"]["solvent"]
                        this[key + "solvent_dict"] = json.dumps(
                            task.drops[drop_idx].solution.solvent_dict
                        )

                else:
                    key = header + c
                    if key in dfdata:
                        this[key] = v
        dfdata.append(this)

    return pd.DataFrame(dfdata)


def assign_hotplates(samples: list):
    temperatures = {}

    for s in samples:
        for task in s.worklist:
            if isinstance(task, Anneal):
                if task.temperature not in temperatures:
                    temperatures[task.temperature] = []
                temperatures[task.temperature].append(task)

    unique_temperatures = list(temperatures.keys())
    unique_temperatures.sort()

    if len(temperatures) > 3:
        raise Exception(
            f"Maximum three unique temperatures allowed: currently requesting {len(temperatures)} ({unique_temperatures})"
        )

    if max(unique_temperatures) > 200:
        raise Exception(
            f"Maximum hotplate temperature allowed is 200°C: currently requesting {max(unique_temperatures)}°C"
        )

    hotplate_settings = {}
    for temperature, hp in zip(unique_temperatures, HOTPLATE_NAMES):
        for task in temperatures[temperature]:
            task.hotplate = hp
            task.workers = [WORKERS[hp]]
        hotplate_settings[hp] = temperature
    return hotplate_settings


def process_sample_list(
    samples: list, sample_trays: list, experiment_name: str
) -> Tuple[pd.DataFrame, dict]:
    for i, s in enumerate(samples):
        s.name = f"sample{i}"
    hotplate_settings = assign_hotplates(samples)
    load_sample_trays(samples, sample_trays)
    df = samples_to_dataframe(samples)

    filename = f"SampleDataframe_{experiment_name}.csv"
    df.to_csv(filename)
    print(f"Sample dataframe saved to {filename}")

    return df, hotplate_settings


#### Set liquid storage locations + amounts needed


def where_to_store(volume, options):
    for ll in options:
        if volume <= ll.volume and len(ll._openwells) > 0:
            return ll
    raise ValueError(f"No options have enough space to hold {volume/1e3:.2f} mL!")


def handle_liquids(samples: list, mixer: mx.Mixer, solution_storage: list):
    solution_details = {}
    for s in mixer.solutions:
        solution_details[s] = {
            "largest_volume_required": round(
                mixer.initial_volumes_required.get(s, 0), 3
            ),
            "is_stock": mixer.solutions.index(s) in mixer.stock_idx,
        }

    for ll in solution_storage:
        ll.unload_all()

    for solution, v in solution_details.items():
        if solution.well["labware"] is None:
            continue
        volume = v["largest_volume_required"]
        # ll = [ll for ll in solution_storage if ll.name == solution.well["labware"]][0]
        # well = ll.load(solution, well=solution.well["well"])
        solution_details[solution]["labware"] = solution.well["labware"]
        solution_details[solution]["well"] = solution.well["well"]
        if v["is_stock"]:
            solution_details[solution]["initial_volume_required"] = v[
                "largest_volume_required"
            ]
        else:
            solution_details[solution]["initial_volume_required"] = 0

    for solution, v in solution_details.items():
        if "labware" in v:
            continue
        volume = v["largest_volume_required"]
        ll = where_to_store(volume, solution_storage)  # which liquid labware
        well = ll.load(solution)
        solution_details[solution]["labware"] = ll.name
        solution_details[solution]["well"] = well
        if v["is_stock"]:
            solution_details[solution]["initial_volume_required"] = v[
                "largest_volume_required"
            ]
        else:
            solution_details[solution]["initial_volume_required"] = 0

    for s in samples:
        for task in s.worklist:
            if not isinstance(task, Spincoat):
                continue
            for drop in task.drops:
                d = solution_details[drop.solution]
                drop.solution.well = {
                    "labware": d["labware"],
                    "well": d["well"],
                }

    mixing_netlist = (
        []
    )  # [{source: {[destinations], [volumes]}}, {source:{[destinations], [volumes]}}]
    for generation in mixer.transfers_per_generation:
        this_generation = {}
        for source, transfers in generation.items():
            labware = solution_details[source]["labware"]
            well = solution_details[source]["well"]
            source_str = f"{labware}-{well}"
            transfers_from_this_source = {}
            for destination, volume in transfers.items():
                if volume == 0:
                    continue
                labware = solution_details[destination]["labware"]
                well = solution_details[destination]["well"]
                destination_str = f"{labware}-{well}"
                transfers_from_this_source[destination_str] = volume.round(2)
            this_generation[source_str] = transfers_from_this_source
        mixing_netlist.append(this_generation)

    return solution_details, mixing_netlist


### Class to bring it all together


class PASCALPlanner:
    def __init__(
        self,
        name: str,
        description: str,
        operator: str,
        samples: list,
        sample_trays: list,
        tip_racks: list,
        solution_storage: list,
        stock_solutions: list,
    ):
        self.name = name
        self.description = description
        self.operator = operator
        self.sample_trays = sample_trays
        self.tip_racks = tip_racks
        self.solution_storage = solution_storage
        self.solution_storage.sort(key=lambda labware: labware.name)
        self.solution_storage.sort(key=lambda labware: labware.volume)
        self.stock_solutions = stock_solutions
        self.samples = self._process_samples(samples=samples, sample_trays=sample_trays)
        self.hotplate_settings = assign_hotplates(self.samples)

    def _process_samples(self, samples, sample_trays):
        """Make sure all samples have a unique name

        Args:
            samples (list): list of Sample objects

        Returns:
            list: list of Sample objects with unique names
        """
        for i, sample in enumerate(samples):
            sample.name = f"sample{i}"
        load_sample_trays(samples, sample_trays)
        return samples

    def process_solutions(
        self, min_volume: float = 50, min_transfer_volume: float = 20, **mixsol_kwargs
    ):
        required_solutions = {}
        for s in self.samples:
            for task in s.worklist:
                if isinstance(task, Spincoat):
                    for d in task.drops:
                        sol = d.solution
                        if sol in required_solutions:
                            required_solutions[sol] += d.volume
                        else:
                            required_solutions[sol] = (
                                d.volume + min_volume
                            )  # minimum volume per well for successful aspiration
        if len(required_solutions) == 0:
            print("No solutions required for this experiment!")
            self.solution_details = {}
            self.mixing_netlist = {}
            return

        if len(self.stock_solutions) == 0:
            raise Exception(
                "Cannot make any solutions because no stock solutions were provided during initalization of PASCALPlanner!"
            )
        self.mixer = mx.Mixer(
            stock_solutions=self.stock_solutions,
            targets=required_solutions,
        )

        default_mixsol_kwargs = dict(
            min_volume=min_transfer_volume,
            max_inputs=4,
            tolerance=1e-4,
            strategy="prefer_stock",
        )

        default_mixsol_kwargs.update(mixsol_kwargs)
        default_mixsol_kwargs
        self.mixer.solve(**default_mixsol_kwargs)
        self.solution_details, self.mixing_netlist = handle_liquids(
            samples=self.samples,
            mixer=self.mixer,
            solution_storage=self.solution_storage,
        )
        self.mixer.print()

    def solve_schedule(self, shuffle=True, prioritize_first_spincoat=False, **kwargs):
        self.system = build()
        if shuffle:
            sample_it = iter(random.sample(self.samples, len(self.samples)))
        else:
            sample_it = iter(self.samples)

        for sample in sample_it:
            sample.protocol = self.system.generate_protocol(
                worklist=sample.worklist, name=sample.name
            )
        breakpoints = []
        if prioritize_first_spincoat:
            for sample in self.samples:
                for task in sample.protocol.worklist:
                    if isinstance(task, Spincoat):
                        breakpoints.append(task)
                        break

        self.system.scheduler.solve(breakpoints=breakpoints, **kwargs)
        self.system.scheduler.plot_solution()
        filename = f"schedule_{self.name}.jpeg"
        plt.savefig(filename, bbox_inches="tight")
        print(f'schedule image saved to "{filename}"')

    def export(self):
        ## plot solution destinations
        ll_with_solutions = [ll for ll in self.solution_storage if len(ll.contents) > 0]

        if len(ll_with_solutions) > 0:
            fig, ax = plt.subplots(
                len(ll_with_solutions), 1, figsize=(6, 4 * len(ll_with_solutions))
            )
            try:
                ax = ax.flat
            except:
                ax = [ax]
            for ll, ax_ in zip(ll_with_solutions, ax):
                ll.plot(solution_details=self.solution_details, ax=ax_)
            plt.savefig(f"solutionmap_{self.name}.jpeg", dpi=150, bbox_inches="tight")

            ## write solution details to csv
            with open(f"stocksolutions_{self.name}.csv", "w", newline="") as f:
                writer = csv.writer(f, delimiter=",")
                header = [
                    "Labware",
                    "Well",
                    "Volume (uL)",
                    "Solutes",
                    "Molarity (M)",
                    "Solvent",
                ]
                writer.writerow(header)
                for solution, details in self.solution_details.items():
                    volume = details["initial_volume_required"]
                    if volume == 0:
                        volume = "Empty Vial"
                    line = [
                        details["labware"],
                        details["well"],
                        volume,
                        solution.solutes,
                        solution.molarity,
                        solution.solvent,
                    ]
                    writer.writerow(line)

        ##plot sample tray map
        st_with_samples = [st for st in self.sample_trays if len(st.contents) > 0]

        if len(st_with_samples) > 0:
            fig, ax = plt.subplots(
                len(st_with_samples), 1, figsize=(3, 4 * len(st_with_samples))
            )
            try:
                ax = ax.flat
            except:
                ax = [ax]
            for ll, ax_ in zip(st_with_samples, ax):
                ll.plot(ax=ax_)
            plt.savefig(f"traymap_{self.name}.jpeg", dpi=150, bbox_inches="tight")

        ## export opentrons protocol
        if any([isinstance(task, Spincoat) for task in self.system.scheduler.tasklist]):
            generate_ot2_protocol(
                title=self.name,
                mixing_netlist=self.mixing_netlist,
                labware=self.solution_storage,
                tipracks=self.tip_racks,
            )

        ## export maestro netlist
        samples_output = {}
        ordered_task_output = []
        for sample in self.samples:
            sd = sample.to_dict()
            samples_output[sample.name] = sd
            ordered_task_output.extend(sd["worklist"])
        ordered_task_output.sort(key=lambda t: t["start"])

        baselines_required = {}
        for task in ordered_task_output:
            if task["name"] != "characterize":
                continue
            for ctask in task["details"]["characterization_tasks"]:
                if ctask["name"] not in baselines_required:
                    baselines_required[ctask["name"]] = set()

                if "exposure_time" in ctask["details"]:
                    baselines_required[ctask["name"]].add(
                        ctask["details"]["exposure_time"]
                    )
                if "exposure_times" in ctask["details"]:
                    for et in ctask["details"]["exposure_times"]:
                        baselines_required[ctask["name"]].add(et)
        baselines_required = {k: list(v) for k, v in baselines_required.items()}

        out = {
            "name": self.name,
            "description": self.description,
            "samples": samples_output,
            # 'tasks': ordered_task_output,
            "baselines_required": baselines_required,
            "hotplate_setpoints": self.hotplate_settings,
        }

        fname = f"maestronetlist_{self.name}.json"
        with open(fname, "w") as f:
            json.dump(out, f, indent=4, sort_keys=True)
        print(f'Maestro Netlist dumped to "{fname}"')

        df = samples_to_dataframe(samples=self.samples)
        fname = f"sampledataframe_{self.name}.csv"
        df.to_csv(fname)
        print(f'Sample dataframe dumped to "{fname}"')
