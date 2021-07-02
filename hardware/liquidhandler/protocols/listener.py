import requests  # you can install this with pip
import time

# status enumerations
STATUS_IDLE = 0
STATUS_TASK_RECEIVED = 1
STATUS_TASK_INPROGRESS = 2


class Listener:
    def __init__(self, address="http://132.239.93.24:8080/update"):
        self.address = address
        self.experiment_in_progress = True
        self.status = 0  # liquid handler status key: 0 = idle, 1 = actively working on task, 2 = completed task, waiting for maestro to acknowlegde
        self.currenttask = None
        self.tipracks = None  # will be set externally in run(). can be any number
        self.stock = None  # set externally. assumes only one stock wellplate!
        self.mixing = None  # set externally. assumes one wellplate to hold mixtures of stock solutions
        self.pipettes = None  # set externally. assumes two pipettes.
        self.spincoater = (
            None  # set externally, has two locations named "standby" and "chuck"
        )

        self.AIRGAP = 20  # airgap, in ul, to aspirate after solution. helps avoid drips, but reduces max tip capacity
        self.DISPENSE_HEIGHT = (
            1  # distance between tip and bottom of wells while dispensing, mm
        )
        self.SPINCOATING_DISPENSE_HEIGHT = 10  # distance between tip and chuck, mm
        self.DISPENSE_RATE = (
            5  # distance between tip and bottom of wells while dispensing, mm
        )
        self.SPINCOATING_DISPENSE_RATE = 50  # distance between tip and chuck, mm
        self.ANTISOLVENT_PIPETTE = 0  # default left pipette for antisolvent
        self.PSK_PIPETTE = 1  # default right for psk
        self.STANDBY_WELL = "B1"
        self.CHUCK_WELL = "A1"

        # tasklist contains all methods to control liquid handler
        self.tasklist = {
            "aspirate_for_spincoating": self.aspirate_for_spincoating,
            "dispense_onto_chuck": self.dispense_onto_chuck,
            "cleanup": self.cleanup,
        }

    def check_for_instructions(self):
        payload = {
            "status": 0,
        }

        r = requests.post(self.address, json=payload)

        r = r.json()

        try:
            if "all_done" in r["kwargs"]:
                return False
        except:
            pass

        if r["pending_requests"] > 0:
            print("identified request")
            self.process_request(
                taskid=r["taskid"],
                function=r["function"],
                args=r["args"],
                kwargs=r["kwargs"],  # keyword arguments
            )

        return True  # flag to indicate whether experiment is completed

    def process_request(self, taskid, function, args, kwargs):
        if function in self.tasklist:
            function = self.tasklist[function]
        else:
            pipette = self.parse_pipette(kwargs["pipette"])
            function = getattr(pipette, function)

        self.taskid = taskid
        self.status = STATUS_TASK_RECEIVED
        payload = {"status": STATUS_TASK_RECEIVED, "taskid": taskid}
        r = requests.post(self.address, json=payload)
        r = r.json()

        function(*args, **kwargs)

        self.status = STATUS_TASK_INPROGRESS
        payload = {"status": STATUS_TASK_INPROGRESS, "taskid": taskid}
        r = requests.post(self.address, json=payload)

        r = r.json()
        if r["completion_acknowledged"]:
            self.status = STATUS_IDLE

    def parse_pipette(self, pipette):
        if type(pipette) is int:
            return self.pipettes[pipette]

        if type(pipette) is str:
            pipette = pipette.lower()
        if pipette in ["psk", "perovskite", "p", "left", "l"]:
            return self.pipettes[self.PSK_PIPETTE]
        elif pipette in ["as", "antisolvent", "a", "right", "r"]:
            return self.pipettes[self.ANTISOLVENT_PIPETTE]
        else:
            raise ValueError("Invalid pipette name given!")

    ### bundled pipetting methods
    def aspirate_for_spincoating(self, psk_well, psk_volume, as_well, as_volume):
        for p in self.pipettes:
            p.pick_up_tip()

        self.pipettes[self.PSK_PIPETTE].aspirate(
            psk_volume, self.stock.wells_by_name()[psk_well]
        )

        self.pipettes[self.PSK_PIPETTE].air_gap(self.AIRGAP)

        self.pipettes[self.ANTISOLVENT_PIPETTE].aspirate(
            as_volume, self.stock.wells_by_name()[as_well]
        )
        self.pipettes[self.ANTISOLVENT_PIPETTE].air_gap(self.AIRGAP)

        self.pipettes[1].move_to(
            self.spincoater[self.STANDBY_WELL].top()
        )  # moves right pipette to standby location of spincoater, which should be to the bottom left of chuck

    def dispense_onto_chuck(self, pipette, height=None, rate=None):
        if height is None:
            height = self.SPINCOATING_DISPENSE_HEIGHT
        if rate is None:
            rate = self.SPINCOATING_DISPENSE_RATE

        pipette = self.parse_pipette(pipette)
        # set dispense settings for spincoating
        pipette.well_bottom_clearance.dispense = (
            height  # set z-offset from chuck to tip, mm
        )

        pipette.flow_rate.dispense = rate  # dispense flow rate, ul/s

        pipette.dispense(location=self.spincoater[self.CHUCK_WELL])

        # set dispense settings to defaults for liquid handling
        pipette.well_bottom_clearance.dispense = self.DISPENSE_HEIGHT
        pipette.flow_rate.dispense = self.DISPENSE_RATE  # dispense flow rate, ul/s

    def cleanup(self):
        for p in self.pipettes:
            p.drop_tip()
        # for p in self.pipettes:
        #     p.pick_up_tip()


metadata = {
    "protocolName": "Maestro Listener",
    "author": "Rishi Kumar",
    "source": "FRG",
    "apiLevel": "2.10",
}


def run(protocol_context):
    listener = Listener()

    listener.tipracks = [
        protocol_context.load_labware("sartorius_safetyspace_tiprack_200ul", slot)
        for slot in ["8"]
    ]

    listener.stock = protocol_context.load_labware("frg_12_wellplate_15000ul", "9")
    listener.pipettes = [
        protocol_context.load_instrument(
            "p300_single_gen2", side, tip_racks=listener.tipracks
        )
        for side in ["left", "right"]
    ]

    listener.spincoater = protocol_context.load_labware(
        "frg_spincoater_v1", "3"
    )  # has two locations defined as "wells", called "standby" and "chuck"

    for p in listener.pipettes:
        p.pick_up_tip()
        p.aspirate(10, listener.stock.wells_by_name()["B2"])  # make this an empty well!
        p.dispense(10, listener.spincoater[listener.CHUCK_WELL])
        p.return_tip()

    if (
        protocol_context.is_simulating()
    ):  # without this, the protocol simulation gets stuck in loop forever.
        return

    experiment_in_progress = True
    timeout = 5 * 60  # timeout, seconds
    time_of_last_response = time.time()
    while experiment_in_progress:
        try:
            experiment_in_progress = listener.check_for_instructions()
            time_of_last_response = time.time()
        except:
            if time.time() - time_of_last_response > timeout:
                print("Timeout")
                experiment_in_progress = False

        time.sleep(0.1)
