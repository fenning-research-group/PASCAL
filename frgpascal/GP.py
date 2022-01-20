from multiprocessing.sharedctypes import Value
import numpy as np
import csv
import pandas as pd
from frgpascal.hardware.sampletray import (
    SampleTray,
    AVAILABLE_VERSIONS as sampletray_versions,
)
import time
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
from frgpascal.bridge import ALClient

from ax.service.ax_client import AxClient
from ax.service.scheduler import Scheduler, SchedulerOptions
from ax.modelbridge.generation_strategy import GenerationStrategy, GenerationStep
from ax.core.runner import Runner
from ax.core.trial import Trial
from ax.core.base_trial import BaseTrial, TrialStatus
from ax import *
from typing import Iterable, Set, Any, Dict, NamedTuple, Union


class PASCALJob(NamedTuple):
    """Dummy class to represent a job scheduled on `MockJobQueue`."""

    id: int
    sample_name: str
    parameters: Dict[str, Union[str, float, int, bool]]


class PASCALJobQueueClient:
    """Dummy class to represent a job queue where the Ax `Scheduler` will
    deploy trial evaluation runs during optimization.
    """

    jobs: Dict[str] = {}

    def schedule_job_with_parameters(
        self, parameters: Dict[str, Union[str, float, int, bool]]
    ) -> int:
        """Schedules an evaluation job with given parameters and returns job ID."""
        # TODO send job to maestro

        job_id = int(time.time())
        self.jobs[job_id] = PASCALJob(job_id, parameters)
        return job_id

    def get_job_status(self, job_id: int) -> TrialStatus:
        """ "Get status of the job by a given ID. For simplicity of the example,
        return an Ax `TrialStatus`.
        """
        job = self.jobs[job_id]
        # Instead of randomizing trial status, code to check actual job status
        # would go here.
        if np.randint(0, 3) > 0:
            return TrialStatus.COMPLETED
        return TrialStatus.RUNNING

    def get_outcome_value_for_completed_job(self, job_id: int) -> Dict[str, float]:
        """Get evaluation results for a given completed job."""
        job = self.jobs[job_id]
        # In a real external system, this would retrieve real relevant outcomes and
        # not a synthetic function value.
        return self.process_data(sample=job.sample_name)

    def process_data(self, sample):
        ### check metric names, load data and return each requested data type
        data = {}
        return data


JOB_QUEUE_CLIENT = PASCALJobQueueClient()


def get_job_queue_client():
    return JOB_QUEUE_CLIENT


class PASCALMetric(Metric):
    def fetch_trial_data(self, trial: BaseTrial, **kwargs: Any) -> Data:
        if not isinstance(trial, Trial):
            raise ValueError("This metric can only handle 'Trial' objects")
        job_queue = get_job_queue_client()

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        data = job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "branin",
            "arm_name": trial.arm.name,
            "mean": data.get("branin"),  # TODO Metric name
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


def make_PASCAL_experiment() -> Experiment:
    parameters = [
        RangeParameter(
            name="antisolvent_volume",
            parameter_type=ParameterType.FLOAT,
            lower=60,
            upper=10,
        ),
        RangeParameter(
            name="antisolvent_rate",
            parameter_type=ParameterType.FLOAT,
            lower=25,
            upper=150,
        ),
        RangeParameter(
            name="antisolvent_timing",
            parameter_type=ParameterType.FLOAT,
            lower=-20,
            upper=-5,
        ),
        RangeParameter(
            name="anneal_duration",
            parameter_type=ParameterType.FLOAT,
            lower=10 * 60,
            upper=60 * 60,
        ),
    ]

    objective = Objective(
        metric=PASCALMetric(name="redplspec_intensity"), minimize=False
    )

    return Experiment(
        name="PASCAL_closedloop",
        search_space=SearchSpace(parameters=parameters),
        optimization_config=OptimizationConfig(objective=objective),
        runner=PASCALRunner(),
        is_test=False,
    )


class PASCALRunner(Runner):
    def run(self, trial: BaseTrial) -> Dict[str, Any]:
        """Deploys a trial based on custom runner subclass implementation.

        Args:
            trial: The trial to deploy.

        Returns:
            Dict of run metadata from the deployment process.
        """
        if not isinstance(trial, Trial):
            raise ValueError("This runner only handles `Trial`.")

        mock_job_queue = get_mock_job_queue_client()
        job_id = mock_job_queue.schedule_job_with_parameters(
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
            mock_job_queue = get_mock_job_queue_client()
            status = mock_job_queue.get_job_status(
                job_id=trial.run_metadata.get("job_id")
            )
            status_dict[status].add(trial.index)

        return status_dict


experiment = make_PASCAL_experiment()
generation_strategy = GenerationStrategy(
    steps=[
        # 1. Initialization step (does not require pre-existing data and is well-suited for
        # initial sampling of the search space)
        GenerationStep(
            model=Models.SOBOL,
            num_trials=5,  # How many trials should be produced from this generation step
            min_trials_observed=3,  # How many trials need to be completed to move to next model
            max_parallelism=5,  # Max parallelism for this step
            model_kwargs={"seed": 999},  # Any kwargs you want passed into the model
            model_gen_kwargs={},  # Any kwargs you want passed to `modelbridge.gen`
        ),
        # 2. Bayesian optimization step (requires data obtained from previous phase and learns
        # from all data available at the time of each new candidate generation call)
        GenerationStep(
            model=Models.GPEI,
            num_trials=20,  # No limitation on how many trials should be produced from this step
            max_parallelism=-1,  # Parallelism limit for this step, often lower than for Sobol
            # More on parallelism vs. required samples in BayesOpt:
            # https://ax.dev/docs/bayesopt.html#tradeoff-between-parallelism-and-total-number-of-trials
        ),
    ]
)

scheduler = Scheduler(
    experiment=experiment,
    generation_strategy=generation_strategy,
    options=SchedulerOptions(),
)


###########
class SingleTaskGP(ALClient):
    def __init__(self):
        #### Solution Storage Slots
        super().__init__()
        self.NUMSAMPLES_INIT = 5
        self.NUMSAMPLES_TOTAL = 35

    ### PASCAL methods
    def initialize_labware(self):
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

    def build_protocol(self, anneal_duration, min_start=None):
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

        self.add_sample(
            sample=sample, min_start=min_start
        )  # solves schedule + sends to maestro

        return sample

    def process_characterization_data(self, sample: str) -> dict:
        """Loads and processes characterization data, returns in
           format appropriate for Ax/BOTorch

        Args:
            sample (str): sample name to look up data

        Returns:
            (dict): characterization results in format:
                {
                    "metric_name": (
                        value,
                        standard error/noise value
                    ),
                    ...
                }
        """
        return {}

    ### BO methods
    # https://ax.dev/tutorials/gpei_hartmann_developer.html
    # https://ax.dev/tutorials/scheduler.html
    # https://ax.dev/tutorials/generation_strategy.html
    def make_experiment(self):
        # self.ax_client = AxClient()

        # self.ax_client.create_experiment(
        #     name="PskBO",
        #     parameters=[
        #         {
        #             "name": "antisolvent_volume",
        #             "type": "range",
        #             "bounds": [60, 200],
        #             "value_type": "int",
        #             "log_scale": False,
        #         },
        #         {
        #             "name": "antisolvent_rate",
        #             "type": "range",
        #             "bounds": [25, 150],
        #             "value_type": "int",
        #             "log_scale": False,
        #         },
        #         {
        #             "name": "antisolvent_timing",
        #             "type": "range",
        #             "bounds": [-20, -5],
        #             "value_type": "int",
        #             "log_scale": False,
        #         },
        #         {
        #             "name": "anneal_duration",
        #             "type": "range",
        #             "bounds": [10 * 60, 60 * 60],
        #             "value_type": "int",
        #             "log_scale": False,
        #         },
        #     ],
        #     objective_name="redplspec_intensity",
        #     minimize=False,
        #     parameter_constraints=[],
        #     outcome_constraints=[],
        # )

        parameters = [
            RangeParameter(
                name="antisolvent_volume",
                parameter_type=ParameterType.FLOAT,
                lower=60,
                upper=10,
            ),
            RangeParameter(
                name="antisolvent_rate",
                parameter_type=ParameterType.FLOAT,
                lower=25,
                upper=150,
            ),
            RangeParameter(
                name="antisolvent_timing",
                parameter_type=ParameterType.FLOAT,
                lower=-20,
                upper=-5,
            ),
            RangeParameter(
                name="anneal_duration",
                parameter_type=ParameterType.FLOAT,
                lower=10 * 60,
                upper=60 * 60,
            ),
        ]
