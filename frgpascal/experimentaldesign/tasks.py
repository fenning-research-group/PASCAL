from ortools.sat.python import cp_model
import matplotlib.pyplot as plt
import numpy as np
import uuid
import json
import yaml
from copy import deepcopy
import os
from mixsol import Solution as Solution_mixsol

from roboflo import Task as Task_roboflo

from frgpascal.hardware import liquidhandler
from frgpascal.workers import (
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_Hotplate,
    Worker_SpincoaterLiquidHandler,
    Worker_Storage,
)


MODULE_DIR = os.path.dirname(__file__)
with open(
    os.path.join(MODULE_DIR, "..", "hardware", "hardwareconstants.yaml"), "r"
) as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


gg = Worker_GantryGripper(planning=True)
sclh = Worker_SpincoaterLiquidHandler(planning=True)
hp = Worker_Hotplate(capacity=25, planning=True)
st = Worker_Storage(capacity=45, planning=True, initial_fill=45)
cl = Worker_Characterization(planning=True)

workers = [gg, sclh, hp, st, cl]

ALL_TASKS = {
    task: {
        "workers": [type(worker)]
        + details.other_workers,  # list of workers required to perform task
        "estimated_duration": details.estimated_duration,  # time (s) to complete task
    }
    for worker in workers
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
        self.worklist = deepcopy(worklist)
        for t in self.worklist:
            t.sample = self
        self.status = "not_started"  # currently unused
        self.tasks = []

    def to_dict(self):
        task_output = {task.id: task.to_dict() for task in self.tasks}

        out = {
            "name": self.name,
            "sampleid": self._sampleid,
            "substrate": self.substrate,
            "storage_slot": self.storage_slot,
            "worklist": [w.to_dict() for w in self.worklist],
            "tasks": task_output,
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
class Solution(Solution_mixsol):
    def __init__(
        self,
        solvent: str,
        solutes: str = "",
        molarity: float = 0,
        labware: str = None,
        well: str = None,
    ):
        super().__init__(solutes=solutes, solvent=solvent, molarity=molarity)
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
        out = {
            "solutes": self.solutes,
            "molarity": self.molarity,
            "solvent": self.solvent,
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
        rate: float = 100,
        height: float = 2,
        slow_retract: bool = True,
        touch_tip: bool = True,
        air_gap: bool = True,
        pre_mix: tuple = (0, 0),
        reuse_tip: bool = False,
        slow_travel: bool = False,
        blow_out: bool = False,
    ):
        self.solution = solution
        if volume <= 0:
            raise ValueError("Volume (uL) must be >0!")
        self.volume = volume
        self.time = time
        if rate < 0 or rate > 200:
            raise ValueError("dispense rate must be 0<rate<=200 uL/sec")
        self.rate = rate

        if height <= 0 or height > 10:
            raise ValueError("dispense height must be 0.5<height<=10 mm")
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
        rate: float = 100,
        height: float = 2,
        slow_retract: bool = False,
        touch_tip: bool = False,
        air_gap: bool = True,
        pre_mix: int = 3,
        reuse_tip: bool = False,
        slow_travel: bool = True,
    ):
        super().__init__(
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
        )


### Base Class for PASCAL Tasks
class Task(Task_roboflo):
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
            "sample": self.sample.name,  # only change to roboflo Task.to_dict()
            "start": self.start,
            "id": self.id,
            "details": self.generate_details(),
        }
        if self.precedent is None:
            out["precedent"] = None
        else:
            out["precedent"] = self.precedent.id

        return out

    def to_json(self):
        return json.dumps(self.to_dict())


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
        if len(drops) > 2:
            raise ValueError(
                "Cannot plan more than two drops in one spincoating routine (yet)!"
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
            return (self.steps == other.steps).all() and all(
                ds in other.drops for ds in self.drops
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
        hotplate: str = "Hotplate1",
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
        if hotplate not in ["Hotplate1", "Hotplate2", "Hotplate3"]:
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
    def __init__(self, duration: float, immediate=True):
        """

        Args:
            duration (float): duration (seconds) to anneal the sample
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
    def __init__(self, duration: float = 240, immediate=False):
        self.duration = duration
        super().__init__(
            task="characterize",
            duration=self.duration,
            immediate=immediate,
        )

    def __repr__(self):
        return "<Characterize>"


### build task list for a sample
def generate_sample_worklist(sample: Sample):
    worklist = deepcopy(sample.worklist)
    for task0, task1 in zip(worklist, worklist[1:]):
        task1.precedent = task0  # task1 is preceded by task0

    sample_tasklist = []
    p0 = Worker_Storage  # sample begins at storage
    for task in worklist:
        task.sample = sample
        p1 = task.workers[0]
        if p0 != p1:
            transition_task = TRANSITION_TASKS[p0][p1]
            if Worker_Hotplate in [p0, p1]:
                immediate = True
            else:
                immediate = task.immediate
            sample_tasklist.append(
                Task(
                    sample=sample,
                    task=transition_task,
                    immediate=immediate,
                    precedent=task.precedent,
                )
            )
            task.precedent = sample_tasklist[-1]
        sample_tasklist.append(task)
        p0 = p1  # update location for next task
    if p1 != Worker_Storage:
        transition_task = TRANSITION_TASKS[p0][Worker_Storage]
        if p1 == Worker_Hotplate:
            immediate = True
        else:
            immediate = False
        sample_tasklist.append(
            Task(
                sample=sample,
                task=transition_task,
                precedent=sample_tasklist[-1],
                immediate=immediate,
            )
        )  # sample ends at storage

    min_start = 0
    for task in sample_tasklist:
        task.min_start = min_start
        min_start += task.duration
    return sample_tasklist
