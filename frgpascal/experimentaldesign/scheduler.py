from ortools.sat.python import cp_model
import matplotlib.pyplot as plt

from frgpascal.workers import (
    Worker_Characterization,
    Worker_GantryGripper,
    Worker_Hotplate,
    Worker_SpincoaterLiquidHandler,
    Worker_Storage,
)
from frgpascal.experimentaldesign.tasks import Task, generate_sample_worklist

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
        self.spanning_tasks = spanning_tasks
        self.enforce_sample_order = enforce_sample_order

    def _generate_worklists(self):
        for s in self.samples:
            s.tasks = generate_sample_worklist(s)
        self.tasks = {s.name: s.tasks for s in self.samples}
        self.tasklist = [
            t for sample_tasks in self.tasks.values() for t in sample_tasks
        ]
        self.horizon = int(sum([t.duration for t in self.tasklist]))

    def _initialize_model(self):
        self._generate_worklists()
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
        if self.enforce_sample_order:
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

    def _generate_ordered_tasklist(self):
        ordered_tasks = [task for sample in self.samples for task in sample.tasks]
        ordered_tasks.sort(key=lambda x: x.start)
        ordered_tasks = self._insert_idlegantry_steps(ordered_tasks)
        return ordered_tasks

    def _insert_idlegantry_steps(self, ordered_tasks):
        gg_tasks = [t for t in ordered_tasks if Worker_GantryGripper in t.workers]
        for precedent, task in zip(gg_tasks, gg_tasks[1:]):
            gantry_idle_time = task.start - precedent.end
            if precedent.task.endswith("to_hotplate") and gantry_idle_time > 10:
                idle_task = Task(
                    task="idle_gantry",
                    sample=precedent.sample,
                    precedent=precedent,
                    immediate=True,
                )
                idle_task.start = precedent.start + 1
                idle_task.end = idle_task.start + idle_task.duration
                ordered_tasks.append(idle_task)

                sample_tasklist = precedent.sample.tasks
                idx = sample_tasklist.index(precedent)
                sample_tasklist.insert(idx + 1, idle_task)
                # print(
                #     f"added idle_gantry between {precedent} and {task} (idle time of {gantry_idle_time} seconds)"
                # )
        ordered_tasks.sort(key=lambda x: x.start)
        return ordered_tasks

    def solve(self, solve_time=5):
        self._initialize_model()
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = solve_time
        status = self.solver.Solve(self.model)

        status_key = {
            0: "UNKNOWN",
            1: "OPTIMAL",
            2: "FEASIBLE",
            3: "INFEASIBLE",
        }
        print(f"solution status: {status_key[status]}")

        for s in self.samples:
            for task in s.tasks:
                task.start = self.solver.Value(task.start_var)
                task.end = self.solver.Value(task.end_var)
        self.plot_solution()
        return self._generate_ordered_tasklist()

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

        xlim0 = plt.xlim()
        plt.hlines(
            [i for i in range(1, len(workers))],
            *xlim0,
            colors="k",
            alpha=0.1,
            linestyles="dotted",
        )
        plt.xlim(xlim0)
        ax = plt.twiny()
        ax.set_xlim([x / 60 for x in xlim0])
        ax.set_xlabel("Time (hours)")

    # def _set_start_time(self, task):
    #     for pid in task.precedents:
    #         ptidx = self.tasks.index(pid)
    #         pt = self.tasks[ptidx]
    #         if pt.end_time < task.start_time:
    #             task.start_time = pt.end_time
