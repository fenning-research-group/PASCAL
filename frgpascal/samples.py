import numpy as np

class SpincoatRecipe:
    def __init__(self, steps: list, perovskite_drop_time: float, antisolvent_drop_time: float):
        """

        Args:
            steps (list): nested list of steps:
            [
                [speed, acceleration, duration],
                [speed, acceleration, duration],
                ...,
                [speed, acceleration, duration]
            ] 
            where speed = rpm, acceleration = rpm/s, duration = s (including the acceleration ramp!)

            perovskite_drop_time (float): timing (seconds) relative to first spin step start to drop precursor solution on substrate. negative values imply dropping the solution prior to spinning (static spincoat)
            antisolvent_drop_time (float): timing (seconds) relative to first spin step start to drop antisolvent on substrate.
        """
        self.steps = np.asarray(steps)
        if self.steps.shape[1] != 3:
            raise ValueError("steps must be an nx3 nested list/array where each row = [speed, acceleration, duration].")
        
        self.perovskite_drop_time = perovskite_drop_time
        self.antisolvent_drop_time = antisolvent_drop_time
        first_drop_time = min(perovskite_drop_time, antisolvent_drop_time)

        self.start_times = [max(0, -first_drop_time)] #push back spinning times to allow static drop beforehand
        for duration in self.steps[:-1,2]:
            self.start_times.append(self.start_times[-1] + duration)
class AnnealRecipe:
    def __init__(self, duration: float, temperature: float):
        """

        Args:
            duration (float): duration (seconds) to anneal the sample
            temperature (float): temperature (C) to anneal the sample at
        """
        self.duration = duration
        self.temperature = temperature
class Sample:
    def __init__(self, name, spincoat: SpincoatRecipe, anneal: AnnealRecipe):
        