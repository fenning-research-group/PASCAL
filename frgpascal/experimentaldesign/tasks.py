class Worker:
    def __init__(self, name, capacity):
        self.name = name
        self.capacity = capacity


gg = Worker(name="gantry_gripper", capacity=1)
sclh = Worker(name="spincoater_liquidhander", capacity=1)
hp = Worker(name="hotplate", capacity=25)
st = Worker(name="storage", capacity=45)
cl = Worker(name="characterizationline", capacity=1)


class Task:
    def __init__(
        self, task, workers, duration, start_time=0, task_details={}, precedents=[]
    ):
        self.worker = worker
        self.task = task
        self.task_details = task_details
        self.taskid = f"{task}-{str(uuid.uuid4())}"
        self.precedentids = precedents
        self.start_time = start_time

    @property
    def start_time(self):
        return self.__start_time

    @start_time.setter
    def start_time(self, t):
        self.__start_time = t
        self.end_time = t + duration

    def __eq__(self, other):
        return other == self.taskid


class StorageToSpincoater(Task):
    def __init__(self, precedents=[]):
        super.__init__(
            task="storage_to_spincoater",
            workers=[gg, sclh],
            duration=30,
            task_details="",
            precedents=precedents,
        )


class Spincoat(Task):
    def __init__(self, recipe: SpincoatRecipe, precedents=[]):
        super.__init__(
            task="spincoat",
            workers=[sclh],
            duration=recipe.duration + 45,
            task_details=recipe.to_json(),
            precedents=precedents,
        )


class SpincoaterToHotplate(Task):
    def __init__(self, precedents=[]):
        super.__init__(
            task="spincoater_to_hotplate",
            workers=[gg, sclh],
            duration=30,
            task_details="",
            precedents=precedents,
        )


class Anneal(Task):
    def __init__(self, recipe: AnnealRecipe, precedents=[]):
        super.__init__(
            task="anneal",
            workers=[hp],
            duration=recipe.duration,
            task_details=recipe.to_json(),
            precedents=precedents,
        )


class HotplateToStorage(Task):
    def __init__(
        self, hotplatetray, hotplateslot, storagetray, storageslot, precedents=[]
    ):
        super.__init__(
            task="hot",
            workers=[gg],
            duration=30,
            task_details=json.dumps(
                {
                    "hotplatetray": hotplatetray,
                    "hotplateslot": hotplateslot,
                    "storagetray": storagetray,
                    "storageslot": storageslot,
                }
            ),
            precedents=precedents,
        )


class Cooldown(Task):
    def __init__(self, precedents=[]):
        super.__init__(
            task="cooldown",
            workers=[st],
            duration=300,
            task_details="",
            precedents=precedents,
        )


class StorageToCharacterization(Task):
    def __init__(self, tray, slot, precedents=[]):
        super.__init__(
            task="storage_to_characterization",
            workers=[gg, cl],
            duration=30,
            task_details=json.dumps({"tray": tray, "slot": slot}),
            precedents=precedents,
        )


class Characterize(Task):
    def __init__(self, precedents=[]):
        super.__init__(
            task="characterize",
            workers=[cl],
            duration=120,
            task_details="",
            precedents=precedents,
        )


class CharacterizationToStorage(Task):
    def __init__(self, tray, slot, precedents=[]):
        super.__init__(
            task="characterization_to_storage",
            workers=[gg, cl],
            duration=30,
            task_details=json.dumps({"tray": tray, "slot": slot}),
            precedents=precedents,
        )

