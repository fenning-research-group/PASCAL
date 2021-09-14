import numpy as np
from uuid import uuid4  # for unique sample identifiers
import json

### Recipes to define a sample
class Solution:
    def __init__(
        self,
        solvent: str,
        solutes: str = "",
        molarity: float = 0,
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
        self,
        name,
        factor=1,
        delimiter="_",
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

    def __str__(self):
        if self.solutes == "":  # no solutes, just a solvent
            return f"{self.solvent}"
        return f"{round(self.molarity,2)}M {self.solutes} in {self.solvent}"

    def __repr__(self):
        return f"<Solution>" + str(self)

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


class Drop:
    def __init__(
        self,
        solution: Solution,
        volume: float,
        time: float,
        rate: float = 50,
        height: float = 2,
    ):
        self.solution = solution
        self.volume = volume
        self.time = time
        self.rate = rate
        self.height = max(
            1, height
        )  # distance from pipette tip to substrate must be at least 1mm

    def __repr__(self):
        return f"<Drop> {self.volume:0.2g} uL of {self.solution} at {self.time}s"

    def to_dict(self):
        out = {
            "type": "drop",
            "solution": self.solution.to_dict(),
            "time": self.time,
            "rate": self.rate,
            "height": self.height,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                self.solution == other.solution
                and self.volume == other.volume
                and self.time == other.time
                and self.rate == other.rate
                and self.height == other.height
            )
        else:
            return False

    def __key(self):
        return (self.solution, self.volume, self.time, self.rate, self.height)

    def __hash__(self):
        return hash(self.__key())


class Spincoat:
    def __init__(
        self,
        steps: list,
        drops: list,
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
            drops: list of solution drops to be performed during spincoating
        """
        self.steps = np.asarray(steps, dtype=float)
        if self.steps.shape[1] != 3:
            raise ValueError(
                "steps must be an nx3 nested list/array where each row = [speed, acceleration, duration]."
            )
        if len(drops) > 2:
            raise ValueError(
                "Cannot plan more than two drops in one spincoating routine (yet)!"
            )
        self.drops = drops
        first_drop_time = min([d.time for d in self.drops])
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
        drops = [d.to_dict() for d in self.drops]

        out = {
            "type": "spincoat",
            "steps": steps,
            "start_times": self.start_times,
            "duration": self.duration,
            "drops": drops,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        output = "<Spincoat>\n"
        currenttime = 0
        psk_dropped = False
        as_dropped = False
        for (rpm, accel, duration) in self.steps:
            output += f"\t{round(currenttime,2)}-{round(currenttime+duration,2)}s:\t{round(rpm,2)} rpm, {round(accel,2):.0f} rpm/s"
            currenttime += duration
            output += "\n"
        for d in self.drops:
            output += "\t" + str(d) + "\n"
        return output[:-1]

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.steps == other.steps).all() and all(
                ds in other.drops for ds in self.drops
            )
        else:
            return False

    def __key(self):
        return (self.steps.tostring(), self.drops)

    def __hash__(self):
        return hash(self.__key())


class Anneal:
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

        return f"<Anneal> {round(self.temperature,1)}C for {round(duration,1)} {units}"

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


class Rest:
    def __init__(self, duration: float):
        """

        Args:
            duration (float): duration (seconds) to anneal the sample
        """
        self.duration = duration

    def __repr__(self):
        duration = self.duration
        units = "seconds"
        if duration > 60:
            duration /= 60
            units = "minutes"
        if duration > 60:
            duration /= 60
            units = "hours"

        return f"<Rest> {round(duration,1)} {units}"

    def to_dict(self):
        out = {
            "type": "rest",
            "duration": self.duration,
        }
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.duration == other.duration
        else:
            return False

    def __key(self):
        return self.duration

    def __hash__(self):
        return hash(self.__key())


class Characterize:
    def __init__(self, duration: float = 200):
        self.duration = duration

    def __repr__(self):
        return "<Characterize>"


class Sample:
    def __init__(
        self,
        name: str,
        substrate: str,
        worklist: list,
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
        self.worklist = worklist
        self.status = "not_started"
        self.tasks = []

    def to_dict(self):
        task_output = [task.to_dict() for task in self.tasks]

        out = {
            "name": self.name,
            "sampleid": self._sampleid,
            "substrate": self.substrate,
            "storage_slot": self.storage_slot,
            "worlist": [w.to_dict() for w in self.worklist],
            "tasks": task_output,
        }

        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        output = f"<Sample> {self.name}\n"
        output += f"<Substrate> {self.substrate}\n"
        output += f"Worklist:\n"
        for task in self.worklist:
            output += f"\t{task}\n"
        return output

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.substrate == other.substrate and self.worklist == other.worklist
        else:
            return False

    def __key(self):
        return (
            self.substrate,
            *self.worklist,
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
        solutes=p["solutes"],
        solvent=p["solvent"],
        molarity=p["molarity"],
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

    return AnnealRecipe(
        duration=p["duration"],
        temperature=p["temperature"],
    )


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
