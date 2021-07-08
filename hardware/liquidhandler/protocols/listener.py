import requests  # you can install this with pip
import time

# status enumerations
STATUS_IDLE = 0
STATUS_TASK_RECEIVED = 1
STATUS_TASK_INPROGRESS = 2


class Listener:
    def __init__(
        self, protocol_context, tips, stocks, spincoater, ip="132.239", port=8765
    ):
        ## Server constants
        self.ip = ip
        self.port = port
        self.address = f"http://{ip}:{port}/update"

        ## Task Tracking
        self.completed_tasks = {}
        self.status = STATUS_IDLE

        ## Labware
        self.tips = tips
        self.pipettes = {
            side: protocol_context.load_instrument(
                "p300_single_gen2", side, tip_racks=self.tips
            )
            for side in ["left", "right"]
        }
        self.stocks = stocks
        self.mixing = mixing  # TODO intermediate mixing wells
        self._sources = {**self.stocks, **self.mixing}
        self.spincoater = spincoater
        self.CHUCK = "A1"
        self.STANDBY = "B1"

        ## Dispense Constants
        self.AIRGAP = 20  # airgap, in ul, to aspirate after solution. helps avoid drips, but reduces max tip capacity
        self.DISPENSE_HEIGHT = (
            1  # mm, distance between tip and bottom of wells while dispensing
        )
        self.DISPENSE_RATE = 10  # uL/s
        self.SPINCOATING_DISPENSE_HEIGHT = 6  # mm, distance between tip and chuck
        self.SPINCOATING_DISPENSE_RATE = 50  # uL/s
        self.SLOW_Z_RATE = 20  # mm/s

        self.ANTISOLVENT_PIPETTE = self.pipettes[
            "left"
        ]  # default left pipette for antisolvent
        self.PSK_PIPETTE = self.pipettes["right"]  # default right for psk

        self.__calibrate_time_to_nist()

        self.tasks = {
            "aspirate_for_spincoating": self.aspirate_for_spincoating,
            "aspirate_both_for_spincoating": self.aspirate_both_for_spincoating,
            "dispense_onto_chuck": self.dispense_onto_chuck,
            "stage_for_dispense": self.stage_for_dispense,
            "cleanup": self.cleanup,
        }

    ### Time Synchronization with NIST

    def __calibrate_time_to_nist(self):
        client = ntplib.NTPClient()
        response = None
        while response is None:
            try:
                response = client.request("europe.pool.ntp.org", version=3)
            except:
                pass
        t_local = time.time()
        self.__local_nist_offset = response.tx_time - t_local

    def nist_time(self):
        return time.time() + self.__local_nist_offset

    ### Communication with Maestro
    def send(self, payload: dict):
        return requests.post(self.address, json=payload)

    def main(self):
        finished = False
        while not finished:
            # ping for new tasks
            maestro = json.loads(websocket.recv())
            if "task" in maestro:
                self.process_task(maestro["task"], websocket)
            if "status" in maestro or len(self.completed_tasks) > 0:
                self.update_status(websocket)
            if "complete" in maestro:
                finished = True
                self.status = STATUS_ALL_DONE

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
                task=r["task"],
                args=r["args"],
                kwargs=r["kwargs"],  # keyword arguments
            )

        return True  # flag to indicate whether experiment is completed

    def process_request(self, task):
        if task["task"] not in self.tasklist:
            return
        else:
            function = self._task
        execution_time = task.pop("nist_time")
        self.status = STATUS_TASK_RECEIVED
        sleep_for = execution_time - self.nist_time()
        if sleep_for > 0:
            time.sleep(sleep_for)
        self.status = STATUS_TASK_INPROGRESS
        function(*task["args"], **task["kwargs"])
        self.status = STATUS_IDLE
        self.completed_tasks[task["taskid"]] = self.nist_time()

        payload = {"status": STATUS_TASK_RECEIVED, "taskid": taskid}
        r = requests.post(self.address, json=payload)
        r = r.json()

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
            return self.PSK_PIPETTE
        elif pipette in ["as", "antisolvent", "a", "right", "r"]:
            return self.ANTISOLVENT_PIPETTE
        else:
            raise ValueError("Invalid pipette name given!")

    ### bundled pipetting methods
    def _aspirate_from_well(
        self, tray, well, volume, pipette, slow_retract, air_gap, touch_tip
    ):
        p = pipette
        if p.has_tip:
            p.drop_tip()
        p.pick_up_tip()
        p.move_to(self._sources[tray][well].bottom(p.well_bottom_clearance.aspirate))
        p.aspirate(volume)
        if slow_retract:
            p.move_to(self._sources[tray][well].top(2), speed=self.SLOW_Z_RATE)
        if air_gap:
            p.air_gap(self.AIRGAP)
        if touch_tip:
            p.touch_tip()

    def aspirate_for_spincoating(
        self,
        tray,
        well,
        volume,
        pipette="perovskite",
        slow_retract=True,
        air_gap=True,
        touch_tip=True,
    ):
        p = self.parse_pipette(pipette=pipette)
        self._aspirate_from_well(
            tray=tray,
            well=well,
            volume=volume,
            pipette=p,
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
        )
        p.move_to(self.spincoater["Standby"].top())

    def aspirate_both_for_spincoating(
        self,
        psk_tray,
        psk_well,
        psk_volume,
        as_tray,
        as_well,
        as_volume,
        slow_retract=True,
        air_gap=True,
        touch_tip=True,
    ):
        for p in self.pipettes.values():
            p.pick_up_tip()

        self._aspirate_from_well(
            tray=psk_tray,
            well=psk_well,
            volume=psk_volume,
            pipette=self.PSK_PIPETTE,
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
        )
        self._aspirate_from_well(
            tray=as_tray,
            well=as_well,
            volume=as_volume,
            pipette=self.ANTISOLVENT_PIPETTE,
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
        )

        self.PSK_PIPETTE.move_to(self.spincoater["Standby"].top())

    def dispense_onto_chuck(self, pipette, height=None, rate=None):
        if height is None:
            height = self.SPINCOATING_DISPENSE_HEIGHT
        elif height < 0:
            height = 0  # negative height = crash into substrate!
        if rate is None:
            rate = self.SPINCOATING_DISPENSE_RATE

        p = self.parse_pipette(pipette)
        relative_rate = rate / p.flow_rate
        p.move_to(self.spincoater["Chuck"].top(height))
        pipette.dispense(location=self.spincoater[self.CHUCK_WELL], rate=relative_rate)

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
    # define your hardware
    tips = [
        protocol_context.load_labware(
            "sartorius_safetyspace_tiprack_200ul", location=location
        )
        for location in ["8"]
    ]

    # note that each stock tray name must match the names from experiment designer!
    stocks = {
        "StockTray1": protocol_context.load_labware(
            "frg_12_wellplate_15000ul", location="9"
        )
    }

    wellplates = {
        "Plate1": protocol_context.load_labware(
            "greiner_96_wellplate_360ul", location="6"
        )
    }

    listener = Listener(
        protocol_context=protocol_context,
        tips=tips,
        stocks=stocks,
        mixing=wellplates,
        spincoater=protocol_context.load_labware("frg_spincoater_v1", location="3"),
    )

    # each piece of labware has to be involved in some dummy moves to be included in protocol
    # we "aspirate" from 10mm above the top of first well on each labware to get it into the protocol
    for side, p in listener.pipettes.items():
        p.pick_up_tip()
        volume = 0
        for name, labware in {**stocks, **wellplates}.items():
            p.aspirate(10, labware["A1"].top(10))
            volume += 10
        p.dispense(volume, listener.spincoater[listener.CHUCK])
        p.return_tip()
        p.reset_tipracks()

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
