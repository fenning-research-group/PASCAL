from ax.core.metric import Metric
from ax.core.base_trial import BaseTrial
from ax.core.data import Data
from ax.core import Trial

import pandas as pd
from frgpascal.closedloop.bridge import PASCALAxQueue


### PL Metrics
class PLIntensity(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "pl_intensity",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("pl_intensity_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


class PLPeak(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "pl_peakev",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("pl_peakev_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


class PLFWHM(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "pl_fhwm",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("pl_fwhm_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


### Photostability Metrics
class PSIntensityScale(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "ps_intensity_scale",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("ps_intensity_scale_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


class PSIntensityRate(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "ps_intensity_rate",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("ps_intensity_rate_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


class PSPeakDelta(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "ps_peakev_delta",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("ps_peakev_delta_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


class PSPeakRate(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "ps_peakev_rate",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("ps_peakev_rate_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


### Transmission Metrics
class TBandgap(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "t_bandgap",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("t_bandgap_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


### Darfield Metrics
class DFMedian(Metric):
    def __init__(self, queue: PASCALAxQueue):
        self.job_queue = queue
        super().__init__()

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.job_queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": "df_median",
            "arm_name": trial.arm.name,
            "mean": sample_data.get("df_median_0"),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))
