import numpy as np
import uuid
import json
import yaml
from copy import deepcopy
import os
import mixsol as mx
from mixsol.helpers import components_to_name
from frgpascal.system import generate_workers
import roboflo

from frgpascal.hardware import liquidhandler
from frgpascal.workers import (
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_Hotplate,
    Worker_SpincoaterLiquidHandler,
    Worker_Storage,
)
from frgpascal.experimentaldesign.characterizationtasks import CharacterizationTask


MODULE_DIR = os.path.dirname(__file__)
with open(
    os.path.join(MODULE_DIR, "..", "hardware", "hardwareconstants.yaml"), "r"
) as f:
    HARDWARECONSTANTS = yaml.load(f, Loader=yaml.FullLoader)

workers = generate_workers()
ALL_TASKS = {
    task: {
        "workers": [worker]
        + details.other_workers,  # list of workers required to perform task
        "estimated_duration": details.estimated_duration,  # time (s) to complete task
    }
    for worker in workers.values()
    for task, details in worker.functions.items()
}

# transition_tasks[source_worker][destination_worker] = Worker_GantryGripper task to move from source to destination
TRANSITION_TASKS = {
    Worker_SpincoaterLiquidHandler: {
        Worker_Hotplate: "spincoater_to_hotplate",
        Worker_Storage: "spincoater_to_storage",
        Worker_Characterization: "spincoater_to_characterization",
    },
    Worker_Hotplate: {
        Worker_SpincoaterLiquidHandler: "hotplate_to_spincoater",
        Worker_Storage: "hotplate_to_storage",
        Worker_Characterization: "hotplate_to_characterization",
    },
    Worker_Storage: {
        Worker_SpincoaterLiquidHandler: "storage_to_spincoater",
        Worker_Hotplate: "storage_to_hotplate",
        Worker_Characterization: "storage_to_characterization",
    },
    Worker_Characterization: {
        Worker_SpincoaterLiquidHandler: "characterization_to_spincoater",
        Worker_Hotplate: "characterization_to_hotplate",
        Worker_Storage: "characterization_to_storage",
    },
}

__hide_me = [
    task for p1 in TRANSITION_TASKS.values() for task in p1.values()
]  # user does not need to see transition tasks
AVAILABLE_TASKS = {
    task: details for task, details in ALL_TASKS.items() if task not in __hide_me
}  # tasks to display to user

### Sample Class


class Sample:
    def __init__(
        self,
        name: str,
        substrate: str,
        worklist: list,
        storage_slot=None,
    ):
        self.name = name
        self.substrate = substrate
        if storage_slot is None:
            self.storage_slot = {
                "tray": None,
                "slot": None,
            }  # tray, slot that sample is stored in. Initialized to None, will be filled when experiment starts
        else:
            self.storage_slot = storage_slot
        self.worklist = [deepcopy(task) for task in worklist]
        for t in self.worklist:
            t.sample = self
        self.status = "not_started"  # currently unused
        self.tasks = []

    def to_dict(self):
        if isinstance(self.protocol, roboflo.Protocol):
            task_output = self.protocol.to_dict()["worklist"]
            for t in task_output:
                t["sample"] = self.name
        else:
            task_output = None

        out = {
            "name": self.name,
            # "sampleid": self._sampleid,
            "substrate": self.substrate,
            "storage_slot": self.storage_slot,
            "worklist": task_output,
        }

        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        output = f"<Sample> {self.name}\n"
        output += f"<Substrate> {self.substrate}\n"
        output += f"Worklist:\n"
        for task in self.worklist:
            output += f"\t{task}\n"
        return output

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.substrate == other.substrate and self.worklist == other.worklist
        else:
            return False

    def __key(self):
        return (
            self.substrate,
            *self.worklist,
        )

    def __hash__(self):
        return hash(self.__key())


### Subclasses to define a spincoat
class Solution(mx.Solution):
    def __init__(
        self,
        solvent: str,
        solutes: str = "",
        molarity: float = 0,
        labware: str = None,
        well: str = None,
        alias: str = None,
    ):
        super().__init__(
            solutes=solutes, solvent=solvent, molarity=molarity, alias=alias
        )
        if solutes != "" and molarity == 0:
            raise ValueError(
                "If the solution contains solutes, the molarity must be >0!"
            )
        if (labware is None and well is not None) or (
            labware is not None and well is None
        ):
            raise Exception(
                "Labware and Well must both be either defined or left as None!"
            )
        self.well = {
            "labware": labware,
            "well": well,
        }  # tray, slot that solution is stored in. Initialized to None, will be filled during experiment planning

    def to_dict(self):
        if self.molarity > 0:
            factor = 1 / self.molarity
        else:
            factor = 1
        out = {
            "solutes": components_to_name(self.solutes, delimiter="_", factor=factor),
            "molarity": self.molarity,
            "solvent": components_to_name(self.solvent, delimiter="_", factor=1),
            "well": self.well,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())


class Drop:
    def __init__(
        self,
        solution: Solution,
        volume: float,
        time: float,
        rate: float = 80,
        height: float = 2,
        slow_retract: bool = True,
        touch_tip: bool = True,
        air_gap: bool = True,
        pre_mix: tuple = (3, 50),
        reuse_tip: bool = False,
        slow_travel: bool = False,
        blow_out: bool = True,
    ):
        self.solution = solution
        if volume <= 0:
            raise ValueError("Volume (uL) must be >0!")
        self.volume = volume
        self.time = time
        if rate < 10 or rate > 2000:
            raise ValueError("dispense rate must be 10<rate<=1000 uL/sec")
        self.rate = rate

        if height < 0 or height > 10:
            raise ValueError("dispense height must be 0<height<=10 mm")
        self.height = (
            height  # distance from pipette tip to substrate must be at least 0.5mm
        )
        self.slow_retract = slow_retract
        self.touch_tip = touch_tip
        self.air_gap = air_gap
        if type(pre_mix) not in [list, tuple, np.array]:
            raise ValueError(
                "pre_mix argument must be a tuple of (n_cycles, volume ul)"
            )
        if len(pre_mix) != 2:
            raise ValueError(
                "pre_mix argument must be a tuple of (n_cycles, volume ul)"
            )
        if pre_mix[0] > pre_mix[1]:
            print(
                f"Possible error: you set pre_mix to {pre_mix[0]} cycles of {pre_mix[1]} ul. Note that the first entry is the number of cycles, and the second entry is the volume in ul to pipette up and down in each cycle."
            )
        self.pre_mix = pre_mix
        self.reuse_tip = reuse_tip
        self.slow_travel = slow_travel
        self.blow_out = blow_out

    def __repr__(self):
        return f"<Drop> {self.volume:0.2g} uL of {self.solution} at {self.time}s"

    def to_dict(self):
        if type(self.solution) is str:
            soldict = self.solution
        else:
            soldict = self.solution.to_dict()
        out = {
            "solution": soldict,
            "volume": self.volume,
            "time": self.time,
            "rate": self.rate,
            "height": self.height,
            "slow_retract": self.slow_retract,
            "touch_tip": self.touch_tip,
            "air_gap": self.air_gap,
            "pre_mix": self.pre_mix,
            "reuse_tip": self.reuse_tip,
            "slow_travel": self.slow_travel,
            "blow_out": self.blow_out,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                self.solution == other.solution
                and self.volume == other.volume
                and self.time == other.time
                and self.rate == other.rate
                and self.height == other.height
            )
        else:
            return False

    def __key(self):
        return (self.solution, self.volume, self.time, self.rate, self.height)

    def __hash__(self):
        return hash(self.__key())


class VolatileDrop(Drop):
    """Wrapper for Drop class with default arguments for handling volatile liquids (like antisolvents)"""

    def __init__(
        self,
        solution: Solution,
        volume: float,
        time: float,
        rate: float = None,
        height: float = None,
        slow_retract: bool = True,  # move slow to prevent drip
        touch_tip: bool = False,
        air_gap: bool = None,
        pre_mix: int = (5, 100),  # pre wet tip to prevent drip
        reuse_tip: bool = None,
        slow_travel: bool = True,  # move slow to prevent drip
        blow_out: bool = None,
    ):
        kwargs = dict(
            solution=solution,
            volume=volume,
            time=time,
            rate=rate,
            height=height,
            slow_retract=slow_retract,
            touch_tip=touch_tip,
            air_gap=air_gap,
            pre_mix=pre_mix,
            reuse_tip=reuse_tip,
            slow_travel=slow_travel,
            blow_out=blow_out,
        )
        kwargs = {
            k: v for k, v in kwargs.items() if v is not None
        }  # drop None arguments, let them default to the Drop default args
        super().__init__(**kwargs)


### Base Class for PASCAL Tasks
class Task(roboflo.Task):
    def __init__(
        self,
        task: str,
        duration: int = None,
        precedent=None,
        immediate: bool = False,
        sample: Sample = None,
        details: dict = {},
    ):
        self.sample = sample
        if task not in ALL_TASKS:
            raise ValueError(f"Task {task} not in ALL_TASKS!")
        self.task = task
        taskinfo = ALL_TASKS[task]
        self.workers = taskinfo["workers"]
        if duration is None:
            duration_ = taskinfo["estimated_duration"]
        else:
            duration_ = int(duration)

        super().__init__(
            name=task,
            workers=taskinfo["workers"],
            duration=duration_,
            precedent=precedent,
            immediate=immediate,
            details=details,
        )

    def __generate_taskid(self):
        self.id = f"{self.task}-{str(uuid.uuid4())}"

    def __repr__(self):
        if self.sample is None:
            return f"<Task> {self.task}, no sample assigned yet"
        else:
            return f"<Task> {self.sample.name}, {self.task}"

    def __eq__(self, other):
        return isinstance(other, self.__class__) and (other.id == self.id)

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, deepcopy(v, memo))

        result.__generate_taskid()  # give a unique id to the copied task
        return result

    def to_dict(self):
        out = {
            "name": self.name,
            "start": self.start,
            "id": self.id,
            "details": self.generate_details(),
        }
        if self.sample is None:
            out["sample"] = "none"
        else:
            out["sample"] = self.sample.name  # only change to roboflo Task.to_dict()

        if self.precedent is None:
            out["precedent"] = None
        else:
            out["precedent"] = self.precedent.id

        return out

    def to_json(self):
        return json.dumps(self.to_dict())


class Mix(Task):
    def __init__(
        self,
        inputs: dict,
        inputs_labware: list,
        destination_labware,
        destination_well: str,
        immediate: bool = False,
    ):
        """Schedule solution mixing on the liquid handler

        Args:
            inputs (dict): dictionary of Solution: volume pairs to be mixed into destination. Solution objects should be present in inputs_labware. Volume should be given in microliters
            inputs_labware (list): list of LiquidLabware objects from which the input Solutions should be sourced.
            destination_labware (list): Destination LiquidLabware object to host the new Solution
            well (str): If provided, will attempt to mix liquid in this specific well.
        """

        self.inputs = {sol: vol for sol, vol in inputs.items() if vol > 0}
        self.inputs_labware = inputs_labware
        self.input_locations = [
            self._get_solution_location(soln) for soln in self.inputs
        ]

        self.destination_labware = destination_labware
        self.destination_well = destination_well
        self.destination_location = (
            f"{self.destination_labware.name}-{self.destination_well}"
        )
        super().__init__(task="mix", duration=self._get_duration(), immediate=immediate)

    def _get_solution_location(self, soln: Solution):
        """Get the location of a solution in the labware"""
        for labware in self.inputs_labware:
            for well, contents in labware.contents.items():
                if contents == soln:
                    return f"{labware.name}-{well}"
        raise ValueError(f"Solution {soln} not found in any labware")

    def _get_duration(self):
        return 40 * len(self.inputs)  # for now assume 40 seconds per solution transfer

    def _generate_mixing_netlist(self):
        return {
            inp_loc: {self.destination_location: inp_volume}
            for inp_loc, inp_volume in zip(self.input_locations, self.inputs.values())
            if inp_volume > 0
        }

    def generate_details(self):
        return {
            "mixing_netlist": self._generate_mixing_netlist(),
            "duration": self.duration,
        }

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.destination_location == other.destination_location
        else:
            return False

    def __key(self):
        return self.destination_location

    def __hash__(self):
        return hash(self.__key())

    def __repr__(self):
        duration = self.duration
        units = "seconds"
        if duration > 60:
            duration /= 60
            units = "minutes"
        if duration > 60:
            duration /= 60
            units = "hours"

        return f"<Mix> {len(self.inputs)} solutions into {self.destination_location}"


class Spincoat(Task):
    def __init__(self, steps: list, drops: list, immediate=False):
        """

        Args:
            steps (list): nested list of steps:
            [
                [speed, acceleration, duration],
                [speed, acceleration, duration],
                ...,
                [speed, acceleration, duration]
            ]
            where speed = rpm, acceleration = rpm/s, duration = s (including the acceleration ramp!)
            drops: list of solution drops to be performed during spincoating
        """
        self.steps = np.asarray(steps, dtype=float)
        if self.steps.shape[1] != 3:
            raise ValueError(
                "steps must be an nx3 nested list/array where each row = [speed, acceleration, duration]."
            )

        if (
            any(
                rpm < HARDWARECONSTANTS["spincoater"]["rpm_min"]
                for rpm in self.steps[:, 0]
                if rpm != 0
            )
            or (self.steps[:, 0] > HARDWARECONSTANTS["spincoater"]["rpm_max"]).any()
        ):
            raise ValueError(
                f"RPM must be either 0 (fully stopped), or between {HARDWARECONSTANTS['spincoater']['rpm_min']} and {HARDWARECONSTANTS['spincoater']['rpm_max']} rpm."
            )
        if (
            self.steps[:, 1] < HARDWARECONSTANTS["spincoater"]["acceleration_min"]
        ).any() or (
            self.steps[:, 1] > HARDWARECONSTANTS["spincoater"]["acceleration_max"]
        ).any():
            raise ValueError(
                f"Acceleration must be between {HARDWARECONSTANTS['spincoater']['acceleration_min']} and {HARDWARECONSTANTS['spincoater']['acceleration_max']} rpm/second."
            )
        if len(drops) not in [1, 2]:
            raise ValueError(
                "Must have either one or two drops per spincoating routine!"
            )
        self.drops = drops
        first_drop_time = min([d.time for d in self.drops])
        self.start_times = [
            max(0, -first_drop_time)
        ]  # push back spinning times to allow static drop beforehand
        for duration in self.steps[:-1, 2]:
            self.start_times.append(self.start_times[-1] + duration)
        duration = self.steps[:, 2].sum() + self.start_times[0]

        # add overhead time based on number of pipetting steps. These numbers are calibrated from experiments
        if len(drops) == 1:
            asp, stage, disp = liquidhandler.expected_timings(drops[0].to_dict())
            duration += max(
                asp + stage + disp - self.drops[0].time,
                0,
            )
        elif len(drops) == 2:
            asp0, stage0, disp0 = liquidhandler.expected_timings(drops[0].to_dict())
            asp1, stage1, disp1 = liquidhandler.expected_timings(drops[1].to_dict())
            duration += max(
                (asp0 + stage0 + disp0) + asp1 - self.drops[0].time,
                0,
            )
        super().__init__(task="spincoat", duration=duration, immediate=immediate)

    def generate_details(self):
        steps = [
            {"rpm": rpm, "acceleration": accel, "duration": duration}
            for rpm, accel, duration in self.steps
        ]
        drops = [d.to_dict() for d in self.drops]

        return {
            "steps": steps,
            "start_times": self.start_times,
            "duration": self.duration,
            "drops": drops,
        }

    def __repr__(self):
        output = "<Spincoat>\n"
        currenttime = 0
        psk_dropped = False
        as_dropped = False
        for (rpm, accel, duration) in self.steps:
            output += f"\t{round(currenttime,2)}-{round(currenttime+duration,2)}s:\t{round(rpm,2)} rpm, {round(accel,2):.0f} rpm/s"
            currenttime += duration
            output += "\n"
        for d in self.drops:
            output += "\t" + str(d) + "\n"
        return output[:-1]

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            if self.steps.shape != other.steps.shape:
                return False
            if len(self.drops) != len(other.drops):
                return False
            return (self.steps == other.steps).all() and all(
                ds == do for ds, do in zip(self.drops, other.drops)
            )
        else:
            return False

    def __key(self):
        return (self.steps.tostring(), self.drops)

    def __hash__(self):
        return hash(self.__key())


class Anneal(Task):
    def __init__(
        self,
        duration: float,
        temperature: float,
        hotplate: str = None,
        immediate=True,
    ):
        """

        Args:
            duration (float): duration (seconds) to anneal the sample
            temperature (float): temperature (C) to anneal the sample at
            hotplate (str): name of the hotplate to use. Must be "Hotplate{1,2,3}"
        """
        self.duration = duration
        self.temperature = temperature
        if hotplate not in [None, "Hotplate1", "Hotplate2", "Hotplate3"]:
            raise ValueError(
                "hotplate must be one of 'Hotplate1', 'Hotplate2', 'Hotplate3'"
            )
        self.hotplate = hotplate
        super().__init__(
            task="anneal",
            duration=self.duration,
            immediate=immediate,
        )

    def __repr__(self):
        duration = self.duration
        units = "seconds"
        if duration > 60:
            duration /= 60
            units = "minutes"
        if duration > 60:
            duration /= 60
            units = "hours"

        return f"<Anneal> {round(self.temperature,1)}C for {round(duration,1)} {units}"

    def generate_details(self):
        return {
            "temperature": self.temperature,
            "duration": self.duration,
            "hotplate": self.hotplate,
        }

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                self.duration == other.duration
                and self.temperature == other.temperature
                and self.hotplate == other.hotplate
            )
        else:
            return False

    def __key(self):
        return (self.duration, self.temperature)

    def __hash__(self):
        return hash(self.__key())


class Rest(Task):
    def __init__(self, duration: float = 300, immediate=True):
        """

        Args:
            duration (float): duration (seconds) to anneal the sample. Default = 5 minutes, typical to cool off sample
        """
        self.duration = duration
        super().__init__(task="rest", duration=self.duration, immediate=immediate)

    def __repr__(self):
        duration = self.duration
        units = "seconds"
        if duration > 60:
            duration /= 60
            units = "minutes"
        if duration > 60:
            duration /= 60
            units = "hours"

        return f"<Rest> {round(duration,1)} {units}"

    def generate_details(self):

        return {
            "duration": self.duration,
        }

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.duration == other.duration
        else:
            return False

    def __key(self):
        return self.duration

    def __hash__(self):
        return hash(self.__key())


class Characterize(Task):
    def __init__(self, tasks, reorder_by_position=False, immediate=False):

        if any([not isinstance(task, CharacterizationTask) for task in tasks]):
            raise Exception(
                "Invalid tasks: `Characterize` method can only execute `CharacterizationMethod` tasks!"
            )
        if reorder_by_position:
            self.characterization_tasks = sorted(
                tasks, key=lambda x: x.position, reverse=True
            )  # starts at the furthest end of the characterization train
        else:
            self.characterization_tasks = tasks

        self.duration = sum(
            [t.expected_duration() for t in self.characterization_tasks]
        )
        self.duration += 10  # buffer time (s)

        positions = [0] + [t.position for t in self.characterization_tasks] + [0]
        m = HARDWARECONSTANTS["characterizationline"]["axis"]["traveltime"]["m"]
        b = HARDWARECONSTANTS["characterizationline"]["axis"]["traveltime"]["b"]
        for p0, p1 in zip(positions, positions[1:]):
            distance = np.abs(p1 - p0)
            self.duration += distance * m + b

        super().__init__(
            task="characterize",
            duration=self.duration,
            immediate=immediate,
        )

    def to_dict(self):
        out = super().to_dict()
        out["duration"] = self.duration
        out["details"] = {
            "characterization_tasks": [t.to_dict() for t in self.characterization_tasks]
        }

        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        s = "<Characterize>"
        for t in self.characterization_tasks:
            s += "\n\t" + t.name
        return s
