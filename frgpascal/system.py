import roboflo as rf
import itertools as itt
from frgpascal.workers import (
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_Hotplate,
    Worker_SpincoaterLiquidHandler,
    Worker_Storage,
)

# define workers
def generate_workers(maestro=None):
    if maestro is None:
        kws = dict(planning=True)
    else:
        kws = dict(maestro=maestro, planning=False)
    gg = Worker_GantryGripper(**kws)
    sclh = Worker_SpincoaterLiquidHandler(**kws)
    hp1 = Worker_Hotplate(capacity=20, **kws)
    hp1.name = "Hotplate1"
    hp2 = Worker_Hotplate(capacity=20, **kws)
    hp2.name = "Hotplate2"
    hp3 = Worker_Hotplate(capacity=20, **kws)
    hp3.name = "Hotplate3"
    st1 = Worker_Storage(capacity=45, initial_fill=45, **kws)
    st1.name = "Tray1"
    st2 = Worker_Storage(capacity=45, initial_fill=45, **kws)
    st2.name = "Tray2"
    cl = Worker_Characterization(**kws)

    return {w.name: w for w in [gg, sclh, hp1, st1, st2, cl]}


ALL_WORKERS = generate_workers()

ALL_TASKS = {}
for worker in ALL_WORKERS.values():
    for task, details in worker.functions.items():
        if task not in ALL_TASKS:
            ALL_TASKS[task] = {
                "workers": [type(worker)]
                + details.other_workers,  # list of workers required to perform task
                "estimated_duration": details.estimated_duration,  # time (s) to complete task
            }

# define transitions

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

transitions = []
for w1, w2 in itt.permutations(ALL_WORKERS.values(), 2):
    t1, t2 = type(w1), type(w2)
    if Worker_GantryGripper in [t1, t2]:
        continue  # no transition tasks for this worker
    if t1 == t2:
        continue  # no transtion between same type (hotplate->hotplate, etc)
    immediate = False
    if Worker_Hotplate in (t1, t2):
        immediate = True  # always get on/off the hotplate at exact time
    if t1 == Worker_SpincoaterLiquidHandler:
        immediate = True  # move off of spincoater ASAP

    transition_name = TRANSITION_TASKS[t1][t2]
    this_transition = rf.Transition(
        duration=ALL_TASKS[transition_name]["estimated_duration"],
        source=w1,
        destination=w2,
        workers=[ALL_WORKERS["GantryGripper"]],
        immediate=immediate,
    )
    this_transition.name = transition_name
    transitions.append(this_transition)


# default system
def build():
    return rf.System(
        workers=list(ALL_WORKERS.values()),
        transitions=transitions,
        starting_worker=ALL_WORKERS["Tray1"],
        ending_worker=ALL_WORKERS["Tray1"],
    )
