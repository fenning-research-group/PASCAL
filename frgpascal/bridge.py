import numpy as np
import os
import time
from queue import Queue
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

    def __init__(self):
        super().__init__()
        self.first_sample_sent = False
        self.__calibrate_time_to_nist()
        self.t0 = None
        self.processed_protocols = []
        self.completed_but_not_processed = Queue()
        self.protocols_in_progress = []

    @property
    def experiment_time(self):
        if self.t0 is None:
            raise Exception(
                "Experiment has not started, or t0 has not been synced to Maestro!"
            )
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
            "sample_complete": self.move_completed_to_queue,
            "set_experiment_directory": self._set_experiment_directory,
        }

        d = json.loads(message)
        func = options[d["type"]]
        func(d)

    def set_start_time(self, delay: int = 5):
        """Update the start time for the current run"""
        self.t0 = self.nist_time + delay
        msg = {"type": "set_start_time", "nist_time": self.t0}
        self.send(json.dump(msg))

    def add_sample(self, sample: dict):
        """Send a new sample to the maestro workers"""
        if not self.first_sample_sent:
            self.set_start_time()  # set maestro overall start time to current time, since this is the first sample!
            self.first_sample_sent = True

        msg = json.dumps(sample)
        self.send(msg)

    def get_experiment_directory(self):
        """
        Get the directory where the experiment is being run
        """
        msg_dict = {"type": "get_experiment_directory"}
        msg = json.dumps(msg_dict)
        self.send(msg)

    def _set_experiment_directory(self, d: dict):
        """
        Set the experiment directory
        """
        self.bridge.experiment_folder = d["path"]


class ALBridge:
    def __init__(self):
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
