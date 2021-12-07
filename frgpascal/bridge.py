import numpy as np
import os
import sys
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
import time
import yaml
import json
import asyncio
from abc import ABC, abstractmethod

from frgpascal.hardware.spincoater import SpinCoater
from frgpascal.hardware.gantry import Gantry
from frgpascal.hardware.gripper import Gripper
from frgpascal.hardware.liquidhandler import OT2
from frgpascal.hardware.hotplate import HotPlate
from frgpascal.hardware.sampletray import SampleTray
from frgpascal.hardware.characterizationline import (
    CharacterizationAxis,
    CharacterizationLine,
)
from frgpascal.workers import (
    Worker_Hotplate,
    Worker_Storage,
    Worker_GantryGripper,
    Worker_Characterization,
    Worker_SpincoaterLiquidHandler,
)


class ALBridge:
    def __init__(self, directory: str, input_space: dict, response_variables: str):
        self.rootdir = directory
        self.protocoldir = os.path.join(self.rootdir, "protocols")
        self.responsedir = os.path.join(self.rootdir, "responses")
        self.consumed_response_files = []
        self.protocols = {}
        self.responses = {}
        self.input_variables = list(input_space.keys())
        self.response_variables = response_variables
        self.X = []
        self.y = []
        self.INTERVAL = 5  # seconds between checking for new response files

    @abstractmethod
    async def build_protocol(self, **inputs) -> dict:
        """convert active learning point into PASCAL experimental protocol"""
        pass

    async def read_response(self, fid) -> dict:
        """read the characterization data file to inform active learner of protocol results

        expects a json file with the following format:
            {
                "name": name of this protocol/sample
                "date": date string,
                "time": time string,
                "inputs":
                    {key:value}
                "responses":
                    {key:value}
                "full_protocol":
                    {full protocol json sent to PASCAL}
            }

        """
        with open(fid, "r") as f:
            data = json.load(f)
            name = data.pop["name"]
            self.responses[data["name"]] = data

            x = [data["inputs"][i] for i in self.input_variables]
            y = [data["responses"][i] for i in self.response_variables]
            self.X.append(x)
            self.y.append(y)
        self.consumed_response_files.append(fid)

    @abstractmethod
    async def propose_protocol(self) -> dict:
        """based on current results, propose the next protocol point to be tested"""
        pass

    async def reader(self):
        while self.running:
            new_fids = [
                fid
                for fid in os.listdir(self.responsedir)
                if fid not in self.consumed_response_files and ".json" in fid
            ]
            for fid in new_fids:
                await self.read_response(os.path.join(self.responsedir, fid))
            await asyncio.sleep(self.INTERVAL)
