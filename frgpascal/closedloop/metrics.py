from lib2to3.pytree import Base
from ax.core.metric import Metric
from ax.core.base_trial import BaseTrial
from ax.core.data import Data
from ax.core import Trial
from abc import ABC, abstractmethod

import pandas as pd
from frgpascal.closedloop.bridge import PASCALAxQueue

import numpy as np


class BasePASCALMetric(ABC, Metric):
    @classmethod
    @property
    @abstractmethod
    def name(self):
        raise NotImplementedError

    @classmethod
    @property
    @abstractmethod
    def lower_is_better(self):
        raise NotImplementedError

    @abstractmethod
    def retrieve_metric(self, sample_data):
        pass

    def __init__(self, queue: PASCALAxQueue, *args, **kwargs):
        self.queue = queue
        Metric.__init__(
            self, name=self.name, lower_is_better=self.lower_is_better, *args, **kwargs
        )

    def fetch_trial_data(self, trial: BaseTrial) -> Data:
        """Obtains data via fetching it from ` for a given trial."""
        if not isinstance(trial, Trial):
            raise ValueError("This metric only handles `Trial`.")

        # Here we leverage the "job_id" metadata created by `MockJobRunner.run`.
        sample_data = self.queue.get_outcome_value_for_completed_job(
            job_id=trial.run_metadata.get("job_id")
        )
        df_dict = {
            "trial_index": trial.index,
            "metric_name": self.name,
            "arm_name": trial.arm.name,
            "mean": self.retrieve_metric(sample_data=sample_data),
            # Can be set to 0.0 if function is known to be noiseless
            # or to an actual value when SEM is known. Setting SEM to
            # `None` results in Ax assuming unknown noise and inferring
            # noise level from data.
            "sem": None,
        }
        return Data(df=pd.DataFrame.from_records([df_dict]))


### PL Metrics
class PLIntensity(BasePASCALMetric):
    lower_is_better = False
    name = "pl_intensity"

    def retrieve_metric(self, sample_data):
        return sample_data.get("pl_intensity_0")


class PLTargetEnergy(BasePASCALMetric):
    lower_is_better = True
    name = None

    def __init__(self, queue: PASCALAxQueue, targetev: float, *args, **kwargs):
        self.name = f"pl_peak_energy_delta_from_{targetev}"
        super().__init__(queue=queue, *args, **kwargs)
        self.targetev = targetev

    def retrieve_metric(self, sample_data):
        peakev = sample_data.get("pl_peak_energy_0")
        delta = np.abs(peakev - self.targetev)
        return delta


class PLFWHM(BasePASCALMetric):
    lower_is_better = True
    name = "pl_fwhm"

    def retrieve_metric(self, sample_data):
        return sample_data.get("pl_fwhm_0")


### Transmission Metrics
class TransmittanceTargetBandgap(BasePASCALMetric):
    lower_is_better = True
    name = None

    def __init__(self, queue: PASCALAxQueue, targetev: float, *args, **kwargs):
        self.name = f"t_bandgap_delta_from_{targetev}"
        super().__init__(queue=queue, *args, **kwargs)
        self.targetev = targetev

    def retrieve_metric(self, sample_data):
        bandgap = sample_data.get("t_bandgap_0")
        delta = np.abs(bandgap - self.targetev)
        return delta


### Darkfield Metrics
class DFMedian(BasePASCALMetric):
    lower_is_better = True
    name = "df_median"

    def retrieve_metric(self, sample_data):
        return sample_data.get("df_median_0")


### Brightfield Metrics


class BFInhomogeneity(BasePASCALMetric):
    lower_is_better = True
    name = "bf_inhomogeneity"

    def retrieve_metric(self, sample_data):
        return sample_data.get("bf_inhomogeneity_0")
