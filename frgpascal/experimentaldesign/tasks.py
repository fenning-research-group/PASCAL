from ortools.sat.python import cp_model
import matplotlib.pyplot as plt
import numpy as np
import uuid
import json

from frgpascal.experimentaldesign.recipes import (
    Sample,
    Spincoat,
    Anneal,
)
from frgpascal.workers import (
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_Hotplate,
    Worker_SpincoaterLiquidHandler,
    Worker_Storage,
)


gg = Worker_GantryGripper(planning=True)
sclh = Worker_SpincoaterLiquidHandler(planning=True)
hp = Worker_Hotplate(n_workers=25, planning=True)
st = Worker_Storage(n_workers=45, planning=True)
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

hide_me = [
    task for p1 in TRANSITION_TASKS.values() for task in p1.values()
]  # user does not need to see transition tasks
AVAILABLE_TASKS = {
    task: details for task, details in ALL_TASKS.items() if task not in hide_me
}  # tasks to display to user


### Subclasses to define a spincoat
class Solution:
    def __init__(
        self,
        solvent: str,
        solutes: str = "",
        molarity: float = 0,
    ):
        if solutes != "" and molarity == 0:
            raise ValueError(
                "If the solution contains solutes, the molarity must be >0!"
            )

        self.solutes = solutes
        self.molarity = molarity
        self.solvent = solvent

        self.solute_dict = self.name_to_components(
            solutes, factor=molarity, delimiter="_"
        )
        self.solvent_dict = self.name_to_components(solvent, factor=1, delimiter="_")
        total_solvent_amt = sum(self.solvent_dict.values())
        self.solvent_dict = {
            k: v / total_solvent_amt for k, v in self.solvent_dict.items()
        }  # normalize so total solvent amount is 1.0
        self.well = {
            "tray": None,
            "slot": None,
        }  # tray, slot that solution is stored in. Initialized to None, will be filled during experiment planning

    def name_to_components(
        self,
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

    def __str__(self):
        if self.solutes == "":  # no solutes, just a solvent
            return f"{self.solvent}"
        return f"{round(self.molarity,2)}M {self.solutes} in {self.solvent}"

    def __repr__(self):
        return f"<Solution>" + str(self)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                self.solutes == other.solutes
                and self.molarity == other.molarity
                and self.solvent == other.solvent
            )
        else:
            return False

    def __key(self):
        return (self.solutes, self.molarity, self.solvent)

    def __hash__(self):
        return hash(self.__key())


class Drop:
    def __init__(
        self,
        solution: Solution,
        volume: float,
        time: float,
        rate: float = 50,
        height: float = 2,
    ):
        self.solution = solution
        self.volume = volume
        self.time = time
        self.rate = rate
        self.height = max(
            1, height
        )  # distance from pipette tip to substrate must be at least 1mm

    def __repr__(self):
        return f"<Drop> {self.volume:0.2g} uL of {self.solution} at {self.time}s"

    def to_dict(self):
        out = {
            "type": "drop",
            "solution": self.solution.to_dict(),
            "time": self.time,
            "rate": self.rate,
            "height": self.height,
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


### Base Class for PASCAL Tasks
class Task:
    def __init__(
        self,
        task,
        duration=None,
        precedent=None,
        immediate=False,
        sample=None,
    ):
        self.sample = sample
        if task not in ALL_TASKS:
            raise ValueError(f"Task {task} not in ALL_TASKS!")
        taskinfo = ALL_TASKS[task]
        self.task = task
        self.workers = taskinfo["workers"]
        if duration is None:
            self.duration = taskinfo["estimated_duration"]
        else:
            self.duration = int(duration)
        # self.task_details = task_details
        self.taskid = f"{task}-{str(uuid.uuid4())}"
        self.precedent = precedent
        if precedent is None:
            immediate = False
        self.immediate = immediate
        # self.reservoir = []
        # if sum([immediate for task, immediate in precedents]) > 1:
        #     raise ValueError("Only one precedent can be immediate!")

    def __repr__(self):
        return f"<Task> {self.sample.name}, {self.task}"

    def __eq__(self, other):
        return other == self.taskid

    def to_dict(self):
        out = {
            "sample": self.sample.name,
            "start": self.start,
            "task": self.task,
            # "details": self.task_details,
            "id": self.taskid,
            "precedents": [
                precedent.taskid for precedent, immediate in self.precedents
            ],
        }
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

        super().__init__(task="spincoat", duration=duration, immediate=immediate)

    def to_dict(self):
        steps = [
            {"rpm": rpm, "acceleration": accel, "duration": duration}
            for rpm, accel, duration in self.steps
        ]
        drops = [d.to_dict() for d in self.drops]

        out = {
            "type": "spincoat",
            "steps": steps,
            "start_times": self.start_times,
            "duration": self.duration,
            "drops": drops,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

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
    def __init__(self, duration: float, temperature: float, immediate=True):
        """

        Args:
            duration (float): duration (seconds) to anneal the sample
            temperature (float): temperature (C) to anneal the sample at
        """
        self.duration = duration
        self.temperature = temperature
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

    def to_dict(self):
        out = {
            "type": "anneal",
            "temperature": self.temperature,
            "duration": self.duration,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                self.duration == other.duration
                and self.temperature == other.temperature
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

    def to_dict(self):
        out = {
            "type": "rest",
            "duration": self.duration,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

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
    def __init__(self, duration: float = 200, immediate=False):
        self.duration = duration
        super().__init__(
            task="characterize",
            duration=self.duration,
            immediate=immediate,
        )

    def __repr__(self):
        return "<Characterize>"


class Sample:
    def __init__(
        self,
        name: str,
        substrate: str,
        worklist: list,
        storage_slot=None,
        sampleid: str = None,
    ):
        self.name = name
        self.substrate = substrate
        if hash is None:
            self._sampleid = str(uuid4())
        else:
            self._sampleid = sampleid
        if storage_slot is None:
            self.storage_slot = {
                "tray": None,
                "slot": None,
            }  # tray, slot that sample is stored in. Initialized to None, will be filled when experiment starts
        else:
            self.storage_slot = storage_slot
        self.worklist = worklist
        self.status = "not_started"
        self.tasks = []

    def to_dict(self):
        task_output = [task.to_dict() for task in self.tasks]

        out = {
            "name": self.name,
            "sampleid": self._sampleid,
            "substrate": self.substrate,
            "storage_slot": self.storage_slot,
            "worlist": [w.to_dict() for w in self.worklist],
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


### build task list for a sample
def generate_sample_worklist(sample: Sample):
    sample_worklist = []
    p0 = Worker_Storage  # sample begins at storage
    for task0, task1 in zip(sample.worklist, sample.worklist[1:]):
        task1.precedent = task0  # task1 is preceded by task0

    for task in sample.worklist:
        task.sample = sample
        p1 = task.workers[0]
        transition_task = TRANSITION_TASKS[p0][p1]
        sample_worklist.append(
            Task(
                sample=sample,
                task=transition_task,
                immediate=task.immediate,
                precedent=task.precedent,
            )
        )
        task.precedent = sample_worklist[-1]
        sample_worklist.append(task)
        p0 = p1  # update location for next task
    if p1 != Worker_Storage:
        transition_task = TRANSITION_TASKS[p0][Worker_Storage]
        if p1 == Worker_Hotplate:
            immediate = True
        else:
            immediate = False
        sample_worklist.append(
            Task(
                sample=sample,
                task=transition_task,
                precedent=sample_worklist[-1],
                immediate=immediate,
            )
        )  # sample ends at storage
    return sample_worklist
