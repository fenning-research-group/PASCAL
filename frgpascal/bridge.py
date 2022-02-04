import numpy as np
import os
import time
from queue import Queue
import json
import asyncio
from abc import ABC, abstractmethod
import ntplib
from frgpascal.experimentaldesign.tasks import Sample
from frgpascal.websocketbridge import Client
from frgpascal import system

from typing import Any, Dict, NamedTuple, Union
import pandas as pd

from ax import *
from ax.core.base_trial import BaseTrial, TrialStatus
from ax.core.metric import Metric
from ax.core.data import Data

from frgpascal.experimentaldesign.tasks import *
from frgpascal.analysis import photoluminescence as PL
from frgpascal.analysis import brightfield

# from frgpascal.bridge import PASCALAxQueue
# from frgpascal.experimentaldesign.protocolwriter import generate_ot2_protocol


class PASCALJob:
    """Dummy class to represent a job scheduled on `MockJobQueue`."""

    # id: int
    # parameters: Dict[str, Union[str, float, int, bool]]


class PASCALAxQueue(Client):
    """
    Websocket client + experiment coordinator, connects to Maestro server
    """

    def __init__(self):
        super().__init__()
        # self.websocket = Client()
        self.experiment_folder = None
        self.t0 = None
        self.__calibrate_time_to_nist()
        self.initialize_experiment()
        self._samplechecker = (
            brightfield.SampleChecker()
        )  # to check if sample was present during characterization, ie drop detection
        self.SCHEDULE_SOLVE_TIME = (
            30  # time allotted (seconds) to determine task schedule
        )
        self.BUFFER_TIME = 10  # grace period (seconds) between schedule solution discovery and actual execution time

    @property
    def experiment_time(self) -> float:
        """time (seconds) since experiment started"""
        if self.t0 is None:
            raise Exception(
                "Experiment has not started, or t0 has not been synced to Maestro!"
            )
        return self.nist_time - self.t0

    @property
    def min_allowable_time(self) -> float:
        """earliest experiment_time (seconds) at which a new task can be scheduled"""
        return self.experiment_time + self.SCHEDULE_SOLVE_TIME + self.BUFFER_TIME

    @property
    def nist_time(self) -> float:
        return time.time() + self.__local_nist_offset

    def initialize_experiment(self):
        self.system = system.build()
        self.sample_counter = 0
        self.first_sample_sent = False
        self.t0 = None
        self.completed_protocols = []
        self.failed_protocols = []
        self.protocols_in_progress = []
        self.initialize_labware()

        self.get_experiment_directory()

    @abstractmethod
    def build_sample(self, parameters) -> Sample:
        """Given a list of parameters from Ax, return a Sample object

        Args:
            parameters (dict): kwargs corresponding to Ax SearchSpace

        Returns:
            (Sample): Sample object to be added to JobQueue, sent to maestro
        """
        return None

    @abstractmethod
    def initialize_labware(self):
        """
        define all:
            - labware
                - solution storage
                - sample trays
            - solutions
        """
        pass

    ### PASCAL Methods
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
            "sample_complete": self._mark_sample_completed,
            "set_experiment_directory": self._set_experiment_directory,
        }

        d = json.loads(message)
        func = options[d["type"]]
        func(d)

    def set_start_time(self, delay: int = 5):
        """Update the start time for the current run"""
        self.t0 = self.nist_time + delay
        msg = {"type": "set_start_time", "nist_time": self.t0}
        self.send(json.dumps(msg))

    def _send_sample_to_maestro(self, sample: Sample, min_start: int = None):
        """Send a new sample to the maestro workers"""
        if not self.first_sample_sent:
            self.set_start_time()
            self.first_sample_sent = True

        if min_start is None:
            min_start = self.min_allowable_time
        min_start = max([min_start, self.min_allowable_time])
        sample.name = f"sample{self.sample_counter}"
        self.sample_counter += 1

        sample.protocol = self.system.generate_protocol(
            name=sample.name,
            worklist=sample.worklist,
            # starting_worker=self.sample_trays[0],
            # ending_worker=self.sample_trays[0],
            min_start=min_start,
        )
        self.system.scheduler.solve(self.SCHEDULE_SOLVE_TIME)

        msg_dict = sample.to_dict()
        with open(
            os.path.join(self.sample_info_folder, f"{sample.name}.json"), "w"
        ) as f:
            json.dump(msg_dict, f, indent=4, sort_keys=True)

        msg_dict["type"] = "protocol"
        msg = json.dumps(msg_dict)
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
        self.experiment_folder = d["path"]
        self.sample_info_folder = os.path.join(self.experiment_folder, "samples")
        os.mkdir(self.sample_info_folder)

    def _mark_sample_completed(self, message):
        sample_name = message["sample"]

        ## check if we have real data (did the sample make it onto the characterization train?)
        brightfield_filepath = os.path.join(
            self.experiment_folder, "Brightfield", f"{sample_name}_brightfield.tif"
        )
        sample_present = self._samplechecker.sample_is_present_fromfile(
            brightfield_filepath, return_probability=False
        )
        self.protocols_in_progress.remove(sample_name)
        if sample_present:
            self.completed_protocols.append(sample_name)
        else:
            self.failed_protocols.append(sample_name)

    ### Ax Methods
    def schedule_job_with_parameters(
        self, parameters: Dict[str, Union[str, float, int, bool]]
    ) -> int:
        """Schedules an evaluation job with given parameters and returns job ID."""
        # Code to actually schedule the job and produce an ID would go here;
        # using timestamp as dummy ID for this example.
        sample = self.build_sample(parameters)
        self._send_sample_to_maestro(sample=sample)
        job_id = sample.name
        self.jobs[job_id] = PASCALJob(job_id, parameters)
        self.protocols_in_progress.append(job_id)
        return job_id

    def get_job_status(self, job_id: str) -> TrialStatus:
        """ "Get status of the job by a given ID. For simplicity of the example,
        return an Ax `TrialStatus`.
        """
        # sample_name = self.jobs[job_id]
        # Instead of randomizing trial status, code to check actual job status
        # would go here.
        # time.sleep(1)
        if job_id in self.failed_protocols:
            return TrialStatus.FAILED
        if job_id in self.completed_protocols:
            return TrialStatus.COMPLETED
        return TrialStatus.RUNNING

    def get_outcome_value_for_completed_job(self, job_id: str) -> Dict[str, float]:
        """Get evaluation results for a given completed job."""
        job = self.jobs[job_id]

        fid = os.path.join(self.experiment_folder, "PL_635", f"{job_id}_pl.csv")
        wl, cps = PL.load_spectrum(fid)
        try:
            fit = PL.fit_spectrum(
                wl=wl, cts=cps, wlmin=650, wlmax=1100, wlguess=730, plot=False
            )
            return {"redplspec_intensity": fit["intensity"]}
        except:
            return {"redplspec_intensity": 0}
