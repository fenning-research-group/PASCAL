from enum import unique
import numpy as np
import itertools
from frgpascal.experimentaldesign.tasks import Solution, Sample, Spincoat, Drop, Anneal
from copy import deepcopy
import uuid
import matplotlib.pyplot as plt
import pandas as pd
import mixsol
from mixsol.mix import _solutions_to_matrix
from frgpascal.system import generate_workers
from frgpascal.workers import Worker_Hotplate

HOTPLATE_NAMES = [
    name
    for name, worker in generate_workers().items()
    if isinstance(worker, Worker_Hotplate)
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


def samples_to_dataframe(samples):
    dfdata = {c: [] for c in ["name", "storage_tray", "storage_slot", "worklist"]}
    for s in samples:
        dfdata["name"].append(s.name)
        dfdata["storage_tray"].append(s.storage_slot["tray"])
        dfdata["storage_slot"].append(s.storage_slot["slot"])
        dfdata["worklist"].append([t.to_dict() for t in s.worklist])

    task_idx = {name: 0 for name in ["spincoat", "anneal", "rest", "characterize"]}

    for step_idx, step in enumerate(samples[0].worklist):
        idx = task_idx[step.task]
        task_idx[step.task] += 1
        header = f"{step.task}{idx}_"
        if step.task == "spincoat":
            cols = []
            for drop_idx, d in enumerate(step.drops):
                for aspect in [
                    "solutes",
                    "solvent",
                    "molarity",
                    "time",
                    "height",
                    "rate",
                ]:
                    cols.append(f"drop{drop_idx}_{aspect}")
            for c in ["steps", "duration"] + cols:
                dfdata[header + c] = []
        else:
            for c in [header + c for c in step.to_dict().get("details", {}).keys()]:
                dfdata[c] = []

        for s in samples:
            for c, v in s.worklist[step_idx].to_dict().get("details", {}).items():
                if c == "drops":
                    for drop_idx, d in enumerate(v):
                        for aspect in ["time", "height", "rate"]:
                            dfdata[header + f"drop{drop_idx}_{aspect}"].append(
                                d[aspect]
                            )
                        for aspect in ["solutes", "solvent", "molarity"]:
                            dfdata[header + f"drop{drop_idx}_{aspect}"].append(
                                d["solution"][aspect]
                            )
                else:
                    key = header + c
                    if key in dfdata:
                        dfdata[key].append(v)

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
        hotplate_settings[hp] = temperature
    return hotplate_settings


#### Set liquid storage locations + amounts needed


def where_to_store(volume, options):
    for ll in options:
        if volume <= ll.volume and len(ll._openwells) > 0:
            return ll
    raise ValueError(f"No options have enough space to hold {volume/1e3:.2f} mL!")


def handle_liquids(samples: list, mixer: mixsol.Mixer, solution_storage: list):
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
        ll = [ll for ll in solution_storage if ll.name == solution.well["labware"]][0]
        well = ll.load(solution, well=solution.well["well"])
        solution_details[solution]["labware"] = ll.name
        solution_details[solution]["well"] = well
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
