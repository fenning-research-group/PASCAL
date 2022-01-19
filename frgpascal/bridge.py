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
import ntplib

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
from frgpascal.websocketbridge import Client


class ALClient(Client):
    """
    Websocket client to connect to Maestro server
    """

    def __init__(self, bridge):
        self.bridge = bridge
        super().__init__()
        self.first_protocol_sent = False
        self.__calibrate_time_to_nist()
        self.t0 = None

    @property
    def experiment_time(self):
        return self.nist_time - self.t0

    @property
    def nist_time(self):
        return time.time() + self.__local_nist_offset

    def __calibrate_time_to_nist(self):
        client = ntplib.NTPClient()
        response = None
        while response is None:
            try:
                response = client.request("europe.pool.ntp.org", version=3)
            except:
                pass
        self.__local_nist_offset = response.tx_time - time.time()

    def _process_message(self, message: str):
        options = {
            "protocol_complete": self.bridge.process_new_data,
            "folder": self._set_experiment_directory,
            "maestro_start_time": self.reset_start_time,
        }

        d = json.loads(message)
        func = options[d["type"]]
        func(d)

    def reset_start_time(self, d: dict):
        """Update the start time for the current run"""
        self.t0 = d["t0"]

    def add_protocol(self, protocol: dict):
        """Send a new protocol to the maestro workers"""
        if not self.first_protocol_sent:
            self.reset_start_time()  # set maestro overall start time to current time, since this is the first protocol!
            self.first_protocol_sent = True

        msg = json.dumps(protocol)
        self.send(msg)

    def get_experiment_directory(self):
        """
        Get the directory where the experiment is being run
        """
        msg_dict = {"type": "folder"}
        msg = json.dumps(msg_dict)
        self.send(msg)

    def _set_experiment_directory(self, d: dict):
        """
        Set the experiment directory
        """
        self.bridge.experiment_folder = d["path"]


class ALBridge:
    def __init__(self):
        # self.protocols = {}
        # self.responses = {}
        # self.input_variables = list(input_space.keys())
        # self.response_variables = response_variables
        # self.X = []
        # self.y = []
        self.websocket = ALClient(bridge=self)
        self.websocket.get_experiment_directory()

    @abstractmethod
    async def build_protocol(self, **inputs) -> dict:
        """convert active learning point into PASCAL experimental protocol"""
        pass

    @abstractmethod
    async def process_new_data(self, fid) -> dict:
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
        pass

    @abstractmethod
    async def propose_protocol(self) -> dict:
        """based on current results, propose the next protocol point to be tested"""
        pass


class ALBridgeOld:
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
