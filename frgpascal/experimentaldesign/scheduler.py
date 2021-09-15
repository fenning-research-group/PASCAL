from ortools.sat.python import cp_model
import matplotlib.pyplot as plt
from frgpascal.workers import (
    Worker_Characterization,
    Worker_GantryGripper,
    Worker_Hotplate,
    Worker_SpincoaterLiquidHandler,
    Worker_Storage,
)

# from frgpascal.experimentaldesign.tasks import workers

workers = {
    Worker_Characterization: 1,
    Worker_GantryGripper: 1,
    Worker_Hotplate: 25,
    Worker_SpincoaterLiquidHandler: 1,
    Worker_Storage: 45,
}

### Task Scheduler
class Scheduler:
    def __init__(self, samples, spanning_tasks=[], enforce_sample_order=False):
        self.workers = workers
        self.samples = samples
        self.tasks = {s.name: s.tasks for s in samples}
        self.tasklist = [
            t for sample_tasks in self.tasks.values() for t in sample_tasks
        ]
        self.horizon = int(sum([t.duration for t in self.tasklist]))
        self.spanning_tasks = spanning_tasks
        self.initialize_model(enforce_sample_order=enforce_sample_order)

    def initialize_model(self, enforce_sample_order: bool):
        self.model = cp_model.CpModel()
        ending_variables = []
        machine_intervals = {w: [] for w in self.workers}
        # reservoirs = {}
        ### Task Constraints
        for task in self.tasklist:
            task.end_var = self.model.NewIntVar(
                task.duration, self.horizon, "end " + str(task.taskid)
            )
            ending_variables.append(task.end_var)

        for task in self.tasklist:
            ## connect to preceding tasks
            if task.immediate:
                task.start_var = task.precedent.end_var
            else:
                task.start_var = self.model.NewIntVar(
                    0, self.horizon, "start " + str(task.taskid)
                )
                if task.precedent is not None:
                    self.model.Add(task.start_var >= task.precedent.end_var)

            ## mark workers as occupied during this task
            interval_var = self.model.NewIntervalVar(
                task.start_var,
                task.duration,
                task.end_var,
                "interval " + str(task.taskid),
            )
            for w in task.workers:
                machine_intervals[w].append(interval_var)

        ### Force sequential tasks to preserve order even if not immediate #TODO this is not generalizable!
        spanning_tasks = {c: [] for c in self.spanning_tasks}
        for sample, tasks in self.tasks.items():
            for t0, t1, t2 in zip(tasks, tasks[1:], tasks[2:]):
                if t1.task in spanning_tasks:
                    duration = self.model.NewIntVar(0, self.horizon, "duration")
                    interval = self.model.NewIntervalVar(
                        t0.start_var, duration, t2.end_var, "sampleinterval"
                    )
                    spanning_tasks[t1.task].append(interval)
        for intervals in spanning_tasks.values():
            self.model.AddNoOverlap(intervals)

        ### Force sample order if flagged
        if enforce_sample_order:
            for preceding_sample, sample in zip(self.samples, self.samples[1:]):
                self.model.Add(
                    sample.tasks[0].start_var > preceding_sample.tasks[0].start_var
                )

        ### Worker Constraints
        for w, capacity in self.workers.items():
            intervals = machine_intervals[w]
            if capacity > 1:
                demands = [1 for _ in machine_intervals[w]]
                self.model.AddCumulative(intervals, demands, capacity)
            else:
                self.model.AddNoOverlap(intervals)
        objective_var = self.model.NewIntVar(0, self.horizon, "makespan")
        self.model.AddMaxEquality(objective_var, ending_variables)
        self.model.Minimize(objective_var)

    def solve(self, solve_time=5):
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = solve_time
        status = self.solver.Solve(self.model)
        print(status)
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
                    y = [list(self.workers.keys()).index(w) + offset] * 2
                    x = [t.start / 60, t.end / 60]
                    plt.plot(x, y, color=color)

        plt.yticks(
            range(len(self.workers)),
            labels=[str(w).split("Worker_")[1][:-2] for w in self.workers],
        )
        plt.xlabel("Time (minutes)")

    # def _set_start_time(self, task):
    #     for pid in task.precedents:
    #         ptidx = self.tasks.index(pid)
    #         pt = self.tasks[ptidx]
    #         if pt.end_time < task.start_time:
    #             task.start_time = pt.end_time
