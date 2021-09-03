from ortools.sat.python import cp_model
import matplotlib.pyplot as plt
import numpy as np
import uuid

from frgpascal.experimentaldesign.recipes import (
    Sample,
    SpincoatRecipe,
    AnnealRecipe,
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
workers = {type(w): w for w in [gg, sclh, hp, st, cl]}

# transition_tasks[source_worker][destination_worker] = Worker_GantryGripper task to move from source to destination
available_tasks = {
    func: taskdetails
    for w in workers.values()
    for func, taskdetails in w.functions.items()
}  # all tasks available
transition_tasks = {
    sclh: {
        hp: "spincoater_to_hotplate",
        st: "spincoater_to_storage",
        cl: "spincoater_to_characterization",
    },
    hp: {
        sclh: "hotplate_to_spincoater",
        st: "hotplate_to_storage",
        cl: "hotplate_to_characterization",
    },
    st: {
        sclh: "storage_to_spincoater",
        hp: "storage_to_hotplate",
        cl: "storage_to_characterization",
    },
    cl: {
        sclh: "characterization_to_spincoater",
        hp: "characterization_to_hotplate",
        st: "characterization_to_storage",
    },
}

### Base Class for PASCAL Tasks
class Task:
    def __init__(
        self,
        sample,
        task,
        workers,
        duration,
        task_details="",
        precedents=[],
        reservoir=[],
    ):
        self.sample = sample
        self.workers = workers
        self.task = task
        self.task_details = task_details
        self.taskid = f"{task}-{str(uuid.uuid4())}"
        self.precedents = precedents
        self.reservoir = []
        if sum([immediate for task, immediate in precedents]) > 1:
            raise ValueError("Only one precedent can be immediate!")
        self.duration = int(duration)

    def __repr__(self):
        return f"<Task> {self.sample.name}, {self.task}"

    def __eq__(self, other):
        return other == self.taskid

    def to_dict(self):
        out = {
            "sample": self.sample.name,
            "start": self.start,
            "task": self.task,
            "details": self.task_details,
            "id": self.taskid,
            "precedents": [
                precedent.taskid for precedent, immediate in self.precedents
            ],
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())


### build task list for a sample
def generate_tasks_for_sample(sample: Sample):
    tasks = []

    tasks.append(StorageToSpincoater(sample=sample, precedents=[]))

    tasks.append(
        Spincoat(
            sample=sample,
            recipe=sample.spincoat_recipe,
            precedents=[(tasks[-1], False)],  # (task, (bool)immediate)
        )
    )

    tasks.append(SpincoaterToHotplate(sample=sample, precedents=[(tasks[-1], True)]))

    tasks.append(
        Anneal(
            sample=sample, recipe=sample.anneal_recipe, precedents=[(tasks[-1], True)]
        )
    )

    tasks.append(HotplateToStorage(sample=sample, precedents=[(tasks[-1], True)]))

    tasks.append(Cooldown(sample=sample, precedents=[(tasks[-1], True)]))

    tasks.append(
        StorageToCharacterization(sample=sample, precedents=[(tasks[-1], False)])
    )

    tasks.append(Characterize(sample=sample, precedents=[(tasks[-1], False)]))

    tasks.append(
        CharacterizationToStorage(sample=sample, precedents=[(tasks[-1], False)])
    )

    return tasks


### Task Scheduler


class Scheduler:
    def __init__(self, samples, spanning_tasks=[], enforce_sample_order=False):
        self.workers = workers
        self.samples = samples
        self.tasks = {s: s.tasks for s in samples}
        self.tasklist = [
            t for sample_tasks in self.tasks.values() for t in sample_tasks
        ]
        self.horizon = int(sum([t.duration for t in self.tasklist]))
        self.spanning_tasks = spanning_tasks
        self.initialize_model(enforce_sample_order=enforce_sample_order)

    def initialize_model(self, enforce_sample_order: bool):
        self.model = cp_model.CpModel()
        ending_variables = []
        machine_intervals = {w: [] for w in self.workers.values()}
        reservoirs = {}
        ### Task Constraints
        for task in self.tasklist:
            task.end_var = self.model.NewIntVar(
                task.duration, self.horizon, "end" + str(task)
            )
            ending_variables.append(task.end_var)

        for task in self.tasklist:
            ## connect to preceding tasks
            immediate_precedent = [
                precedent for precedent, immediate in task.precedents if immediate
            ]  # list of immediate precedents
            if len(immediate_precedent) == 0:
                task.start_var = self.model.NewIntVar(
                    0, self.horizon, "start" + str(task)
                )
            else:
                precedent = immediate_precedent[0]
                task.start_var = precedent.end_var

            for precedent, immediate in task.precedents:
                if not immediate:
                    self.model.Add(task.start_var >= precedent.end_var)

            ## mark workers as occupied during this task
            interval_var = self.model.NewIntervalVar(
                task.start_var, task.duration, task.end_var, "interval" + str(task)
            )
            for w in task.workers:
                machine_intervals[w].append(interval_var)

        ### Force sequential tasks to preserve order even if not immediate
        spanning_tasks = {c: [] for c in self.spanning_tasks}
        for sample, tasks in self.tasks.items():
            for start_class, end_class in spanning_tasks:
                start_var = [t for t in tasks if t.__class__ == start_class][
                    0
                ].start_var
                end_var = [t for t in tasks if t.__class__ == end_class][0].end_var

                duration = self.model.NewIntVar(0, self.horizon, "duration")
                interval = self.model.NewIntervalVar(
                    start_var, duration, end_var, "sampleinterval"
                )
                spanning_tasks[(start_class, end_class)].append(interval)
        for intervals in spanning_tasks.values():
            self.model.AddNoOverlap(intervals)

        ### Force sample order if flagged
        if enforce_sample_order:
            for preceding_sample, sample in zip(self.samples, self.samples[1:]):
                self.model.Add(
                    sample.tasks[0].start_var > preceding_sample.tasks[0].start_var
                )

        ### Worker Constraints
        for w in workers:
            intervals = machine_intervals[w]
            if w.capacity > 1:
                demands = [1 for _ in machine_intervals[w]]
                self.model.AddCumulative(intervals, demands, w.capacity)
            else:
                self.model.AddNoOverlap(intervals)
        for w, r in reservoirs.items():
            self.modelAddReservoirConstraint(r["times"], r["demands"], 0, w.capacity)
        objective_var = self.model.NewIntVar(0, self.horizon, "makespan")
        self.model.AddMaxEquality(objective_var, ending_variables)
        self.model.Minimize(objective_var)

    def solve(self, solve_time=5):
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = solve_time
        status = self.solver.Solve(self.model)
        for s in self.samples:
            for task in s.tasks:
                task.start = self.solver.Value(task.start_var)
                task.end = self.solver.Value(task.end_var)
        self.plot_solution()

    def plot_solution(self, ax=None):
        plt.figure(figsize=(14, 5))

        for idx, (sample, tasklist) in enumerate(self.tasks.items()):
            color = plt.cm.tab20(idx % 20)
            offset = 0.2 + 0.6 * (idx / len(self.tasks))
            for t in tasklist:
                for w in t.workers:
                    y = [self.workers.index(w) + offset] * 2
                    x = [t.start / 60, t.end / 60]
                    plt.plot(x, y, color=color)

        plt.yticks(range(len(self.workers)), labels=[w.name for w in self.workers])
        plt.xlabel("Time (minutes)")

    # def _set_start_time(self, task):
    #     for pid in task.precedents:
    #         ptidx = self.tasks.index(pid)
    #         pt = self.tasks[ptidx]
    #         if pt.end_time < task.start_time:
    #             task.start_time = pt.end_time
