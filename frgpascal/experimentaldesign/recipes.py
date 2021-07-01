import numpy as np


class SpincoatRecipe:
    def __init__(
        self, steps: list, perovskite_droptime: float, antisolvent_droptime: float
    ):
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
            raise ValueError(
                "steps must be an nx3 nested list/array where each row = [speed, acceleration, duration]."
            )

        self.perovskite_droptime = perovskite_droptime
        self.antisolvent_droptime = antisolvent_droptime
        first_drop_time = min(perovskite_droptime, antisolvent_droptime)

        self.start_times = [
            max(0, -first_drop_time)
        ]  # push back spinning times to allow static drop beforehand
        for duration in self.steps[:-1, 2]:
            self.start_times.append(self.start_times[-1] + duration)

        self.duration = (
            self.steps[:, 2].sum() + 10
        )  # total duration + 10 seconds for stopping

    def __repr__(self):
        output = "<SpincoatingRecipe>\n"
        output += f"Perovskite drops at {self.perovskite_droptime} s\n"
        output += f"Antisolvent drops at {self.antisolvent_droptime} s\n"
        currenttime = 0
        psk_dropped = False
        as_dropped = False
        for (rpm, accel, duration) in self.steps:
            output += f"{currenttime}-{currenttime+duration}s:\t{rpm:.0f} rpm, {accel:.0f} rpm/s"
            currenttime += duration
            if not psk_dropped and self.perovskite_droptime <= currenttime:
                output += " (perovskite dropped)"
                psk_dropped = True
            if not as_dropped and self.antisolvent_droptime <= currenttime:
                output += " (antisolvent dropped)"
                as_dropped = True
            output += "\n"
        return output[:-1]


class AnnealRecipe:
    def __init__(self, duration: float, temperature: float):
        """

        Args:
            duration (float): duration (seconds) to anneal the sample
            temperature (float): temperature (C) to anneal the sample at
        """
        self.duration = duration
        self.temperature = temperature

    def __repr__(self):
        output = "<AnnealRecipe>\n"
        output += f"{self.temperature:.2f} C\n"
        if self.duration >= 3600:
            output += f"{self.duration/3600:.2f} hours"
        elif self.duration >= 60:
            output += f"{self.duration/60:.2f} minutes"
        else:
            output += f"{self.duration:.2f} seconds"
        return output


class Sample:
    def __init__(
        self, name, spincoat_recipe: SpincoatRecipe, anneal_recipe: AnnealRecipe
    ):
        self.name = name
        self.storage_slot = {
            "tray": None,
            "slot": None,
        }  # tray, slot that sample is stored in. Initialized to None, will be filled when experiment starts
        self.spincoat_recipe = spincoat_recipe
        self.anneal_recipe = anneal_recipe
        # self._generate_moves()
        self.status = "not_started"

    # def _generate_moves(self):
    #     """
    #     dictionary of all steps this sample will go through for experiment
    #     """
    #     self.moves = collections.OrderedDict()

    #     self.moves['storagetospincoater'] = move_type(machines=["Gantry", "Spincoater"], duration=30)
    #     self.moves['spincoat'] = move_type(machines=["Spincoater"], duration=self.spincoat_recipe.duration)
    #     self.moves['spincoatertohotplate'] = move_type(machines=["Gantry", "Spincoater"], duration=30)
    #     self.moves['anneal'] = move_type(machines=["Hotplate"], duration=self.anneal_recipe.duration)
    #     self.moves['hotplatetostorage'] = move_type(machines=["Gantry"], duration=30)
    #     self.moves['cooldown'] = move_type(machines=["Storage"], duration=60*2)
    #     self.moves['storagetocharacterization'] = move_type(machines=["Gantry", "Characterization"], duration=30)
    #     self.moves['characterization'] = move_type(machines=["Characterization"], duration=60*4)
    #     self.moves['characterizationtostorage'] = move_type(machines=["Gantry", "Characterization"], duration=30)

    def __repr__(self):
        output = "<Sample>\n"
        output += f"name:\t{self.name}\n"
        output += f"status:\t{self.status}\n"
        output += f"{self.storage_slot}\n"
        output += f"\n{sc[0]}\n\n{an[0]}"
        return output