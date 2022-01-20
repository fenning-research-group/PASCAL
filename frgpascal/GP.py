import numpy as np
import csv
import pandas as pd
from frgpascal.hardware.sampletray import (
    SampleTray,
    AVAILABLE_VERSIONS as sampletray_versions,
)
from frgpascal.hardware.liquidlabware import (
    TipRack,
    LiquidLabware,
    AVAILABLE_VERSIONS as liquid_labware_versions,
)
from frgpascal.hardware.hotplate import AVAILABLE_VERSIONS as hotplate_versions
from frgpascal.experimentaldesign.helpers import (
    build_sample_list,
    plot_tray,
    handle_liquids,
    samples_to_dataframe,
    load_sample_trays,
)
from frgpascal.experimentaldesign.tasks import *
from frgpascal.experimentaldesign.scheduler import Scheduler
from frgpascal.experimentaldesign.protocolwriter import generate_ot2_protocol
import mixsol as mx

# import roboflo as rf
from random import shuffle

from frgpascal import system
import roboflo
from frgpascal.bridge import ALClient


# class BOSimulation:


# def class_to_worker(worker_class):
#     for w in ALL_WORKERS.values():
#         if isinstance(w, worker_class):
#             return w
#     raise Exception(
#         "Could not find a matching worker for class {}".format(worker_class)
#     )
# def generate_protocol(sample: Sample, system: roboflo.System, min_start: int = 0):
#     tray = [
#         w
#         for w in system.workers
#         if isinstance(w, Worker_Storage) and w.name == sample.storage_slot["tray"]
#     ][0]
#     # print(hotplate)

#     for task in sample.worklist:
#         corrected_workers = []
#         for worker in task.workers:
#             if worker in system.ALL_WORKERS.values():
#                 corrected_workers.append(worker)
#             elif worker == Worker_Hotplate:
#                 corrected_workers.append(
#                     [
#                         w
#                         for w in system.workers
#                         if isinstance(w, Worker_Hotplate) and w.name == task.hotplate
#                     ][0]
#                 )
#             elif worker == Worker_Storage:
#                 corrected_workers.append(tray)
#             else:
#                 corrected_workers.append(class_to_worker(worker))
#         task.workers = corrected_workers
#         task.sample = sample

#     sample.protocol = system.generate_protocol(
#         name=sample.name,
#         worklist=sample.worklist,
#         starting_worker=tray,
#         ending_worker=tray,
#         min_start=min_start,
#     )


class SingleTaskGP(ALClient):
    def __init__(self):
        #### Solution Storage Slots
        super().__init__()
        self.system = system.build()  # TODO wtf is this function name
        self.SCHEDULE_SOLVE_TIME = 2
        self.BUFFER_TIME = 2  # seconds of grace period to give between solution discovery and actual execution time
        self.initialize_experiment()

    def initialize_experiment(self):
        ### Hardware
        # Solution Storage
        self.solution_storage = [
            LiquidLabware(
                name="96_Plate1",
                version="greiner_96_wellplate_360ul",
                deck_slot=5,
                # starting_well="C1"
            ),
            LiquidLabware(
                name="4mL_Tray1", version="frg_24_wellplate_4000ul", deck_slot=6
            ),
        ]
        self.solution_storage.sort(key=lambda labware: labware.name)
        self.solution_storage.sort(key=lambda labware: labware.volume)
        # Sample Tray
        self.sample_trays = [
            SampleTray(name="Tray1", version="storage_v1", gantry="", gripper="")
        ]

        ### Solutions
        self.absorber = Solution(
            solutes="MA_Pb_I3",
            solvent="DMF3_DMSO1",
            molarity=1,
            labware="4mL_Tray1",
            well="A1",
        )
        self.antisolvent = Solution(
            solvent="MethylAcetate", labware="4mL_Tray1", well="D4"
        )

        self.sample_counter = 0

    def build_protocol(self, anneal_duration, min_start=None):
        if not self.first_sample_sent:
            self.set_start_time()
            self.first_sample_sent = True

        min_allowable_start = (
            self.experiment_time + self.SCHEDULE_SOLVE_TIME + self.BUFFER_TIME
        )  # cant schedule too early or we cant actually execute
        if min_start is None:
            min_start = min_allowable_start
        min_start = max([min_start, min_allowable_start])
        # spincoat_absorber = Spincoat(
        #     steps=[
        #         [3000, 2000, 50],  # speed (rpm), acceleration (rpm/s), duration (s)
        #     ],
        #     drops=[
        #         Drop(
        #             solution=self.absorber,  # this will be filled later using the list of psk solutions
        #             volume=20,
        #             time=-1,
        #             blow_out=True,
        #         ),
        #         Drop(
        #             solution=self.antisolvent,
        #             volume=drop_volume,
        #             time=drop_time,
        #             reuse_tip=True,
        #             touch_tip=False,
        #             rate=drop_rate,
        #             pre_mix=(5, 50),
        #             slow_travel=True,
        #         ),
        #     ],
        # )
        anneal_absorber = Anneal(temperature=100, duration=anneal_duration)

        name = f"sample{self.sample_counter}"
        sample = Sample(
            name=name,
            substrate="placeholder",
            worklist=[
                # spincoat_absorber,
                anneal_absorber,
                # Rest(180),
                Characterize(),
            ],
            storage_slot={
                "tray": self.sample_trays[0].name,
                "slot": self.sample_trays[0].load(name),
            },
        )
        sample.protocol = self.system.generate_protocol(
            name=sample.name,
            worklist=sample.worklist,
            # starting_worker=self.sample_trays[0],
            # ending_worker=self.sample_trays[0],
            min_start=min_start,
        )
        self.system.scheduler.solve(self.SCHEDULE_SOLVE_TIME)
        self.add_sample(sample=sample.to_dict())
        self.sample_counter += 1

        return sample
