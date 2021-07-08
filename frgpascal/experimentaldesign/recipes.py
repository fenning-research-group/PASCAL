import numpy as np
import yaml
from uuid import uuid4  # for unique sample identifiers
import json


class SpincoatRecipe:
    def __init__(
        self,
        steps: list,
        solution_volume: float,
        solution_droptime: float,
        antisolvent: str = None,
        antisolvent_volume: float = 0,
        antisolvent_droptime: float = np.inf,
        solution: str = None,
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
            antisolvent (str): species of antisolvent. default = None
            antisolvent_drop_time (float): timing (seconds) relative to first spin step start to drop antisolvent on substrate. default = None
        """
        self.steps = np.asarray(steps, dtype=float)
        if self.steps.shape[1] != 3:
            raise ValueError(
                "steps must be an nx3 nested list/array where each row = [speed, acceleration, duration]."
            )

        self.solution = (
            solution  # default None, will be filled by combination with solution mesh
        )
        self.solution_volume = solution_volume
        self.solution_droptime = solution_droptime

        self.antisolvent = antisolvent
        self.antisolvent_volume = antisolvent_volume
        self.antisolvent_droptime = antisolvent_droptime

        first_drop_time = min(solution_droptime, antisolvent_droptime)
        self.start_times = [
            max(0, -first_drop_time)
        ]  # push back spinning times to allow static drop beforehand
        for duration in self.steps[:-1, 2]:
            self.start_times.append(self.start_times[-1] + duration)
        self.duration = self.steps[:, 2].sum() + self.start_times[0]

    def to_json(self):
        steps = [
            {"rpm": rpm, "acceleration": accel, "duration": duration}
            for rpm, accel, duration in self.steps
        ]
        solution = {
            "solution": self.solution,
            "volume": self.solution_volume,
            "droptime": self.solution_droptime,
        }
        antisolvent = {
            "solution": self.antisolvent,
            "volume": self.antisolvent_volume,
            "droptime": self.antisolvent_droptime,
        }

        out = {
            "steps": steps,
            "start_times": self.start_times,
            "duration": self.duration,
            "solution": solution,
            "antisolvent": antisolvent,
        }
        return json.dumps(out)

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
            if not psk_dropped and self.solution_droptime <= currenttime:
                output += " (perovskite dropped)"
                psk_dropped = True
            if not as_dropped and self.antisolvent_droptime <= currenttime:
                output += " (antisolvent dropped)"
                as_dropped = True
            output += "\n"
        return output[:-1]


def spincoatrecipe_fromjson(s: str):
    p = json.loads(s)

    steps = [[s["rpm"], s["acceleration"], s["duration"]] for s in p["steps"]]

    return SpincoatRecipe(
        steps=steps,
        solution=p["solution"]["solution"],
        solution_volume=p["solution"]["volume"],
        solution_droptime=p["solution"]["droptime"],
        antisolvent=p["antisolvent"]["solution"],
        antisolvent_volume=p["antisolvent"]["volume"],
        antisolvent_droptime=p["antisolvent"]["droptime"],
    )


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

    def export(self, filepath):
        output = {"temperature": self.temperature, "duration": self.duration}
        with open(filepath, "w") as f:
            yaml.dump(output, f)


class Sample:
    def __init__(
        self,
        name: str,
        spincoat_recipe: SpincoatRecipe,
        anneal_recipe: AnnealRecipe,
        hashid: str = None,
    ):
        self.name = name
        if hash is None:
            self._hashid = str(uuid4())
        else:
            self._hashid = hashid
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

    def export(self, filepath):
        steps_dict = [
            {"rpm": s[0], "acceleration": s[1], "duration": s[2], "start_time": st}
            for s, st in zip(
                self.spincoat_recipe.steps, self.spincoat_recipe.start_times
            )
        ]
        spincoat_output = {
            "steps": steps_dict,
            "perovskite_drop_time": self.spincoat_recipe.perovskite_droptime,
            "antisolvent_drop_time": self.spincoat_recipe.antisolvent_droptime,
        }
        anneal_output = {
            "temperature": self.anneal_recipe.temperature,
            "duration": self.anneal_recipe.duration,
        }

        out = {
            "name": self.name,
            "hashid": self._hashid,
            "storage_slot": self.storage_slot,
            "spincoat_recipe": self.spincoat_recipe,
            "anneal_recipe": self.anneal_recipe,
        }