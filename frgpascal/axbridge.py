from typing import Any, Dict, NamedTuple, Union
import pandas as pd

from ax import *
from ax.core.base_trial import BaseTrial, TrialStatus
from ax.core.metric import Metric
from ax.core.data import Data

from frgpascal.experimentaldesign.tasks import *
from frgpascal.hardware.liquidlabware import (
    TipRack,
    LiquidLabware,
    AVAILABLE_VERSIONS as liquid_labware_versions,
)
from frgpascal.hardware.sampletray import (
    SampleTray,
    AVAILABLE_VERSIONS as sampletray_versions,
)
from frgpascal.analysis import photoluminescence as PL
from frgpascal.bridge import PASCALAxQueue
from frgpascal.experimentaldesign.protocolwriter import generate_ot2_protocol


### Init, will change per experiment
search_space = SearchSpace(
    parameters=[
        RangeParameter(
            name="antisolvent_volume",
            parameter_type=ParameterType.FLOAT,
            lower=30,
            upper=150,
        ),
        RangeParameter(
            name="antisolvent_rate",
            parameter_type=ParameterType.FLOAT,
            lower=30,
            upper=150,
        ),
        RangeParameter(
            name="antisolvent_timing",
            parameter_type=ParameterType.FLOAT,
            lower=-30,
            upper=-5,
        ),
        RangeParameter(
            name="anneal_duration",
            parameter_type=ParameterType.FLOAT,
            lower=15 * 60,
            upper=60 * 60,
        ),
    ]
)

liquid_labware = [
    LiquidLabware(name="4mL_Tray", version="frg_24_wellplate_4000ul", deck_slot=6)
]
liquid_labware[0].load("dummy")
generate_ot2_protocol(
    title="ClosedLoop",
    mixing_netlist={},
    labware=liquid_labware,
    tipracks=[
        TipRack(
            version="sartorius_safetyspace_tiprack_200ul",
            deck_slot=8,
            starting_tip="A8",
        ),
        TipRack(
            version="sartorius_safetyspace_tiprack_200ul",
            deck_slot=9,
            starting_tip="D5",
        ),
    ],
)
### Ax Components
class PASCALJob:
    """Dummy class to represent a job scheduled on `MockJobQueue`."""

    # id: int
    # parameters: Dict[str, Union[str, float, int, bool]]

    def __init__(self, job_id, parameters):
        self.job_id = job_id
        self.parameters = parameters


class JobQueue(PASCALAxQueue):
    ### PASCAL methods
    def __init__(self):
        super().__init__()
        self.jobs = {}

    def initialize_labware(self):
        self.tipracks = [
            TipRack(
                version="sartorius_safetyspace_tiprack_200ul",
                deck_slot=7,
                starting_tip="A8",
            ),
            TipRack(
                version="sartorius_safetyspace_tiprack_200ul",
                deck_slot=8,
                starting_tip="D5",
            ),
        ]
        self.liquidlabware = [
            LiquidLabware(
                name="4mL_Tray", version="frg_24_wellplate_4000ul", deck_slot=6
            )
        ]
        self.sampletray = SampleTray(
            name="Tray1", version="storage_v1", gantry=None, gripper=None, p0=[0, 0, 0]
        )
        self.solutions = {
            "methylacetate": Solution(
                solvent="MethylAcetate",
                labware="4mL_Tray",
                well="D1",
            ),
            "absorber": Solution(
                solutes="FA0.78_MA0.1_Cs0.12_(Pb_(I0.8_Br0.1_I0.1)3)1.09",
                solvent="DMF3_DMSO1",
                molarity=1.2,
                labware="4mL_Tray",
                well="A1",
            ),
        }

    def build_sample(
        self, parameters: Dict[str, Union[str, float, int, bool]]
    ) -> Sample:
        spincoat_absorber = Spincoat(
            steps=[
                [3000, 2000, 50],  # speed (rpm), acceleration (rpm/s), duration (s)
            ],
            drops=[
                Drop(
                    solution=self.solutions[
                        "absorber"
                    ],  # this will be filled later using the list of psk solutions
                    volume=20,
                    time=-1,
                    blow_out=True,
                    # pre_mix = (5,50),
                ),
                Drop(
                    solution=self.solutions["methylacetate"],
                    volume=parameters["antisolvent_volume"],
                    time=50 + parameters["antisolvent_timing"],
                    reuse_tip=True,
                    touch_tip=False,
                    rate=parameters["antisolvent_rate"],
                    pre_mix=(3, 100),
                    slow_travel=True,
                ),
            ],
        )
        anneal_absorber = Anneal(
            temperature=100, duration=parameters["anneal_duration"]
        )

        samplename = f"sample{self.sample_counter}"
        sample = Sample(
            name=samplename,
            substrate="1mm glass",
            worklist=[spincoat_absorber, anneal_absorber, Rest(180), Characterize()],
            storage_slot={
                "tray": self.sampletray.name,
                "slot": self.sampletray.load(samplename),
            },
        )
        return sample

    ### Ax methods
    def schedule_job_with_parameters(
        self, parameters: Dict[str, Union[str, float, int, bool]]
    ) -> int:
        """Schedules an evaluation job with given parameters and returns job ID."""
        # Code to actually schedule the job and produce an ID would go here;
        # using timestamp as dummy ID for this example.
        sample = self.build_sample(parameters)
        self.add_sample(sample=sample)
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


MOCK_JOB_QUEUE_CLIENT = JobQueue()


def get_mock_job_queue_client() -> JobQueue:
    """Obtain the singleton job queue instance."""
    return MOCK_JOB_QUEUE_CLIENT


### Metrics


class PLBrightnessMetric(Metric):  # Pulls data for trial from external system.
    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        mock_job_queue = get_mock_job_queue_client()

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = mock_job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "redplspec_intensity",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("redplspec_intensity"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))
