from collections import defaultdict
import numpy as np
import os
import time
import json
from abc import ABC, abstractmethod
import ntplib
from frgpascal.experimentaldesign.tasks import Sample
from frgpascal.closedloop.websocket import Client
from frgpascal import system

from typing import Any, Dict, NamedTuple, Union, Iterable, Set

from ax import *
from ax.core.base_trial import BaseTrial, TrialStatus

from frgpascal.analysis.processing import load_sample
from frgpascal.analysis import brightfield
from frgpascal.experimentaldesign.tasks import Rest

WORKERS = system.generate_workers()


class NumpyFloatValuesEncoder(json.JSONEncoder):
    """Converts np.float32 to float to allow dumping to json file"""

    def default(self, obj):
        if isinstance(obj, np.float32):
            return float(obj)
        return json.JSONEncoder.default(self, obj)


class PASCALJob:
    def __init__(self, job_id, parameters):
        self.job_id = job_id
        self.parameters = parameters
        self.outcome = {}
        self.status = TrialStatus.RUNNING


class PASCALAxQueue(Client):
    """
    Websocket client + experiment coordinator, connects to Maestro server

    note that job_id is sample_name is sample.name
    """

    def __init__(self):
        super().__init__()
        # self.websocket = Client()
        self.experiment_folder = None
        self.t0 = None
        self.__calibrate_time_to_nist()
        self.initialize_experiment()
        # self._samplechecker = (
        #     brightfield.SampleChecker()
        # )  # to check if sample was present during characterization, ie drop detection
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
        self.jobs = {}
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
        self.sample_counter += 1

        tray_worker = WORKERS[sample.storage_slot["tray"]]
        for task in sample.worklist:  # make sure sample is resting in its storage tray
            if isinstance(task, Rest):
                task.workers = [tray_worker]
        sample.protocol = self.system.generate_protocol(
            name=sample.name,
            worklist=sample.worklist,
            starting_worker=tray_worker,
            ending_worker=tray_worker,
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
        self.characterization_folder = os.path.join(
            self.experiment_folder, "Characterization"
        )
        os.mkdir(self.sample_info_folder)

    def _mark_sample_completed(self, message):
        sample_name = message["sample"]

        ## check if we have real data (did the sample make it onto the characterization train?)
        # brightfield_filepath = os.path.join(
        #     self.characterization_folder,
        #     sample_name,
        #     "characterization0",
        #     f"{sample_name}_brightfield.tif",
        # )  # TODO only checks failures/dropped samples in the first characterization!
        # sample_present = self._samplechecker.sample_is_present_fromfile(
        #     brightfield_filepath, return_probability=False
        # )

        sample_present = True

        if sample_present:
            outcome = load_sample(
                sample=sample_name, datadir=self.characterization_folder
            )
            outcome["success"] = True
            self.jobs[sample_name].status = TrialStatus.COMPLETED

        else:
            outcome = {"success": False}
            self.jobs[sample_name].status = TrialStatus.FAILED
        self.jobs[sample_name].outcome = outcome

        # save results to sample json file
        with open(
            os.path.join(self.sample_info_folder, f"{sample_name}.json"), "r"
        ) as f:
            sample_dict = json.load(f)
        sample_dict["outcome"] = outcome
        with open(
            os.path.join(self.sample_info_folder, f"{sample_name}.json"), "w"
        ) as f:
            json.dump(
                sample_dict, f, indent=4, sort_keys=True, cls=NumpyFloatValuesEncoder
            )

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
        return job_id

    def get_job_status(self, job_id: str) -> TrialStatus:
        """ "Get status of the job by a given ID. For simplicity of the example,
        return an Ax `TrialStatus`.
        """
        return self.jobs[job_id].status

    def get_outcome_value_for_completed_job(self, job_id: str) -> Dict[str, float]:
        """Get evaluation results for a given completed job."""
        # update the sample info file with outcomes
        # with open(os.path.join(self.sample_info_folder, f"{job_id}.json"), "r") as f:
        #     sample_dict = json.load(f)
        return self.jobs[job_id].outcome


class PASCALRunner(Runner):  # Deploys trials to external system.
    def __init__(self, queue: PASCALAxQueue):
        self._pascalqueue = queue
        super().__init__()

    def run(self, trial: BaseTrial) -> Dict[str, Any]:
        """Deploys a trial based on custom runner subclass implementation.

        Args:
            trial: The trial to deploy.

        Returns:
            Dict of run metadata from the deployment process.
        """
        if not isinstance(trial, Trial):
            raise ValueError("This runner only handles `Trial`.")

        job_id = self._pascalqueue.schedule_job_with_parameters(
            parameters=trial.arm.parameters
        )
        # This run metadata will be attached to trial as `trial.run_metadata`
        # by the base `Scheduler`.
        return {"job_id": job_id}

    def poll_trial_status(
        self, trials: Iterable[BaseTrial]
    ) -> Dict[TrialStatus, Set[int]]:
        """Checks the status of any non-terminal trials and returns their
        indices as a mapping from TrialStatus to a list of indices. Required
        for runners used with Ax ``Scheduler``.

        NOTE: Does not need to handle waiting between polling calls while trials
        are running; this function should just perform a single poll.

        Args:
            trials: Trials to poll.

        Returns:
            A dictionary mapping TrialStatus to a list of trial indices that have
            the respective status at the time of the polling. This does not need to
            include trials that at the time of polling already have a terminal
            (ABANDONED, FAILED, COMPLETED) status (but it may).
        """
        status_dict = defaultdict(set)
        for trial in trials:
            status = self._pascalqueue.get_job_status(
                job_id=trial.run_metadata.get("job_id")
            )
            status_dict[status].add(trial.index)

        return status_dict
