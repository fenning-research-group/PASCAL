from bridge import ALBridge
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
from random import shuffle


class SingleTaskGP(ALBridge):
    def __init__(self, directory: str):
        #### Solution Storage Slots
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
        # sort by volume,name
        self.solution_storage.sort(key=lambda labware: labware.name)
        self.solution_storage.sort(key=lambda labware: labware.volume)
        print("Priority Fill Order:")
        for ss in self.solution_storage:
            print(f"\t{ss}")

        #### Solutions
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

    def build_protocol(self, drop_volume, drop_time, drop_rate, anneal_duration):
        spincoat_absorber = Spincoat(
            steps=[
                [3000, 2000, 50],  # speed (rpm), acceleration (rpm/s), duration (s)
            ],
            drops=[
                Drop(
                    solution=self.absorber,  # this will be filled later using the list of psk solutions
                    volume=20,
                    time=-1,
                    blow_out=True,
                ),
                Drop(
                    solution=self.antisolvent,
                    volume=drop_volume,
                    time=drop_time,
                    reuse_tip=True,
                    touch_tip=False,
                    rate=drop_rate,
                    pre_mix=(5, 50),
                    slow_travel=True,
                ),
            ],
        )

        anneal_absorber = Anneal(temperature=100, duration=anneal_duration)
