import numpy as np
from uuid import uuid4  # for unique sample identifiers
import json

### Recipes to define a sample


class SolutionRecipe:
    def __init__(
        self, solvent: str, solutes: str = "", molarity: float = 0,
    ):
        if solutes != "" and molarity == 0:
            raise ValueError(
                "If the solution contains solutes, the molarity must be >0!"
            )
        self.solutes = solutes
        self.molarity = molarity
        self.solvent = solvent

        self.solute_dict = self.name_to_components(
            solutes, factor=molarity, delimiter="_"
        )
        self.solvent_dict = self.name_to_components(solvent, factor=1, delimiter="_")
        total_solvent_amt = sum(self.solvent_dict.values())
        self.solvent_dict = {
            k: v / total_solvent_amt for k, v in self.solvent_dict.items()
        }  # normalize so total solvent amount is 1.0
        self.well = {
            "tray": None,
            "slot": None,
        }  # tray, slot that solution is stored in. Initialized to None, will be filled during experiment planning

    def name_to_components(
        self, name, factor=1, delimiter="_",
    ):
        """
        given a chemical formula, returns dictionary with individual components/amounts
        expected name format = 'MA0.5_FA0.5_Pb1_I2_Br1'.
        would return dictionary with keys ['MA, FA', 'Pb', 'I', 'Br'] and values [0.5,.05,1,2,1]*factor
        """
        components = {}
        for part in name.split(delimiter):
            species = part
            count = 1.0
            for l in range(len(part), 0, -1):
                try:
                    count = float(part[-l:])
                    species = part[:-l]
                    break
                except:
                    pass
            if species == "":
                continue
            components[species] = count * factor
        return components

    def to_dict(self):
        out = {
            "solutes": self.solutes,
            "molarity": self.molarity,
            "solvent": self.solvent,
            "well": self.well,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        if self.solutes == "":  # no solutes, just a solvent
            return f"<SolutionRecipe> {self.solvent}"
        return f"<SolutionRecipe> {round(self.molarity,2)}M {self.solutes} in {self.solvent}"

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                self.solutes == other.solutes
                and self.molarity == other.molarity
                and self.solvent == other.solvent
            )
        else:
            return False

    def __key(self):
        return (self.solutes, self.molarity, self.solvent)

    def __hash__(self):
        return hash(self.__key())


class SpincoatRecipe:
    def __init__(
        self,
        steps: list,
        solution_volume: float,
        solution_droptime: float,
        antisolvent: SolutionRecipe = None,
        antisolvent_volume: float = 0,
        antisolvent_droptime: float = np.inf,
        solution: SolutionRecipe = None,
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

        self.antisolvent = antisolvent  # default None = no antisolvent
        self.antisolvent_volume = antisolvent_volume
        self.antisolvent_droptime = antisolvent_droptime

        first_drop_time = min(solution_droptime, antisolvent_droptime)
        self.start_times = [
            max(0, -first_drop_time)
        ]  # push back spinning times to allow static drop beforehand
        for duration in self.steps[:-1, 2]:
            self.start_times.append(self.start_times[-1] + duration)
        self.duration = self.steps[:, 2].sum() + self.start_times[0]

    def to_dict(self):
        steps = [
            {"rpm": rpm, "acceleration": accel, "duration": duration}
            for rpm, accel, duration in self.steps
        ]
        solution = {
            "solution": self.solution.to_dict() if self.solution is not None else None,
            "volume": self.solution_volume,
            "droptime": self.solution_droptime,
        }
        antisolvent = {
            "solution": self.antisolvent.to_dict()
            if self.antisolvent is not None
            else None,
            "volume": self.antisolvent_volume,
            "droptime": self.antisolvent_droptime,
        }

        out = {
            "type": "spincoat",
            "steps": steps,
            "start_times": self.start_times,
            "duration": self.duration,
            "solution": solution,
            "antisolvent": antisolvent,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        output = "<SpincoatingRecipe>\n"
        output += f"Solution drops at {self.solution_droptime} s\n"
        output += f"Antisolvent drops at {self.antisolvent_droptime} s\n"
        currenttime = 0
        psk_dropped = False
        as_dropped = False
        for (rpm, accel, duration) in self.steps:
            output += f"{round(currenttime,2)}-{round(currenttime+duration,2)}s:\t{round(rpm,2)} rpm, {round(accel,2):.0f} rpm/s"
            currenttime += duration
            if not psk_dropped and self.solution_droptime <= currenttime:
                output += " (solution dropped)"
                psk_dropped = True
            if not as_dropped and self.antisolvent_droptime <= currenttime:
                output += " (antisolvent dropped)"
                as_dropped = True
            output += "\n"
        return output[:-1]

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                (self.steps == other.steps).all()
                and self.solution == other.solution
                and self.solution_volume == other.solution_volume
                and self.solution_droptime == other.solution_droptime
                and self.antisolvent == other.antisolvent
                and self.antisolvent_volume == other.antisolvent_volume
                and self.antisolvent_droptime == other.antisolvent_droptime
            )
        else:
            return False

    def __key(self):
        return (
            self.steps.tostring(),
            self.solution,
            self.solution_volume,
            self.solution_droptime,
            self.antisolvent,
            self.antisolvent_volume,
            self.antisolvent_droptime,
        )

    def __hash__(self):
        return hash(self.__key())


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
        duration = self.duration
        units = "seconds"
        if duration > 60:
            duration /= 60
            units = "minutes"
        if duration > 60:
            duration /= 60
            units = "hours"

        return f"<AnnealRecipe> {round(self.temperature,1)}C for {round(duration,1)} {units}"

    def to_dict(self):
        out = {
            "type": "anneal",
            "temperature": self.temperature,
            "duration": self.duration,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                self.duration == other.duration
                and self.temperature == other.temperature
            )
        else:
            return False

    def __key(self):
        return (self.duration, self.temperature)

    def __hash__(self):
        return hash(self.__key())


class Sample:
    def __init__(
        self,
        name: str,
        substrate: str,
        spincoat_recipe: SpincoatRecipe,
        anneal_recipe: AnnealRecipe,
        storage_slot=None,
        sampleid: str = None,
    ):
        self.name = name
        self.substrate = substrate
        if hash is None:
            self._sampleid = str(uuid4())
        else:
            self._sampleid = sampleid
        if storage_slot is None:
            self.storage_slot = {
                "tray": None,
                "slot": None,
            }  # tray, slot that sample is stored in. Initialized to None, will be filled when experiment starts
        else:
            self.storage_slot = storage_slot
        self.spincoat_recipe = spincoat_recipe
        self.anneal_recipe = anneal_recipe
        self.status = "not_started"
        self.tasks = []

    def to_dict(self):
        task_output = [task.to_dict() for task in self.tasks]

        out = {
            "name": self.name,
            "sampleid": self._sampleid,
            "substrate": self.substrate,
            "storage_slot": self.storage_slot,
            "spincoat_recipe": self.spincoat_recipe.to_dict(),
            "anneal_recipe": self.anneal_recipe.to_dict(),
            "tasks": task_output,
        }

        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        output = f"<Sample> {self.name}\n"
        output += f"<Substrate> {self.substrate}\n"
        output += f"{self.spincoat_recipe.solution}\n"
        output += f"{self.spincoat_recipe}\n"
        output += f"{self.anneal_recipe}\n"
        return output

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                self.name == other.name
                and self.substrate == other.substrate
                and self.spincoat_recipe == other.spincoat_recipe
                and self.anneal_recipe == other.anneal_recipe
            )
        else:
            return False

    def __key(self):
        return (
            self.substrate,
            *self.spincoat_recipe._SpincoatRecipe__key(),
            *self.anneal_recipe._AnnealRecipe__key(),
        )

    def __hash__(self):
        return hash(self.__key())


### Json -> recipe methods


def solutionrecipe_fromjson(s: str):
    """
    Loads a solution recipe from a json string
    Args:
        s (str): json string
    Returns:
        SolutionRecipe
    """
    p = json.loads(s)

    return SolutionRecipe(
        solutes=p["solutes"], solvent=p["solvent"], molarity=p["molarity"],
    )


def spincoatrecipe_fromjson(s: str):
    """given an input json string, return a new SpincoatRecipe object.

    Args:
        s (str): json string

    Returns:
        SpincoatRecipe: spincoat recipe
    """
    p = json.loads(s)

    steps = [[s["rpm"], s["acceleration"], s["duration"]] for s in p["steps"]]
    if p["solution"] is not None:
        p["solution"] = SolutionRecipe(
            solutes=p["solution"]["solution"]["solutes"],
            molarity=p["solution"]["solution"]["molarity"],
            solvent=p["solution"]["solution"]["solvent"],
        )
    if p["antisolvent"] is not None:
        p["antisolvent"] = SolutionRecipe(
            solutes=p["antisolvent"]["solution"]["solutes"],
            molarity=p["antisolvent"]["solution"]["molarity"],
            solvent=p["antisolvent"]["solution"]["solvent"],
        )

    return SpincoatRecipe(
        steps=steps,
        solution=p["solution"]["solution"],
        solution_volume=p["solution"]["volume"],
        solution_droptime=p["solution"]["droptime"],
        antisolvent=p["antisolvent"]["solution"],
        antisolvent_volume=p["antisolvent"]["volume"],
        antisolvent_droptime=p["antisolvent"]["droptime"],
    )


def annealrecipe_fromjson(s: str):
    """given an input json string
    return an AnnealRecipe object.

    Args:
        s (str): json string

    Returns:
        AnnealRecipe: anneal recipe
    """
    p = json.loads(s)

    return AnnealRecipe(duration=p["duration"], temperature=p["temperature"],)


def sample_fromjson(s: str):
    """given an input json string, return a new Sample object.

    Args:
        s (str): json string
    Returns:
        Sample: sample
    """
    p = json.loads(s)

    return Sample(
        name=p["name"],
        storage_slot=p["storage_slot"],
        substrate=p["substrate"],
        spincoat_recipe=spincoatrecipe_fromjson(p["spincoat_recipe"]),
        anneal_recipe=annealrecipe_fromjson(p["anneal_recipe"]),
        sampleid=p["hashid"],
    )


def from_json(s: str):
    """
    given an input json string s of any recipe type, return a new instance of that recipe in the proper class
    """
    p = json.loads(s)

    recipe_key = {
        "solution": solutionrecipe_fromjson,
        "spincoat": spincoatrecipe_fromjson,
        "anneal": annealrecipe_fromjson,
        "sample": sample_fromjson,
    }
    if p["type"] in recipe_key:
        return recipe_key[p["type"]](p)
    else:
        raise ValueError(
            f"{p['type']} is not a valid recipe type. Supported types are {list(recipe_key.keys())}"
        )
