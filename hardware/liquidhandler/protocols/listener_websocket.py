import asyncio
import websockets
import json
import time

# status enumerations
STATUS_IDLE = 0
STATUS_TASK_RECEIVED = 1
STATUS_TASK_INPROGRESS = 2
# STATUS_TASK_COMPLETE = 3
STATUS_ALL_DONE = 9


class Listener:
    def __init__(
        self,
        protocol_context,
        tips,
        stocks,
        spincoater,
        address="ws://132.239.93.24",
        port=8080,
    ):
        self.address = address
        self.protocol_context = protocol_context
        self.experiment_in_progress = True
        self.status = STATUS_IDLE  # liquid handler status key: 0 = idle, 1 = actively working on task, 2 = completed task, waiting for maestro to acknowlegde
        self.currenttask = None
        self.tips = tips
        self.stocks = stocks
        self.mixing = {}  # TODO intermediate mixing wells
        self._sources = {**self.stocks, **self.mixing}
        self.spincoater = spincoater
        self.pipettes = {
            side: protocol_context.load_instrument(
                "p300_single_gen2", side, tip_racks=self.tips
            )
            for side in ["left", "right"]
        }
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

        # tasklist contains all methods to control liquid handler
        self.tasklist = {
            "aspirate_for_spincoating": self.aspirate_for_spincoating,
            "dispense_onto_chuck": self.dispense_onto_chuck,
            "cleanup": self.cleanup,
        }

        # queue stuff
        queue = asyncio.PriorityQueue()

    def start_listening(self):
        listen_to_maestro = websockets.serve(hello, self.address, self.port)
        asyncio.get_event_loop().run_until_complete(self.main)

    async def main(self, websocket, path):
        while self.status != STATUS_ALL_DONE:
            if self.status == STATUS_IDLE:  # listen for updates from maestro
                maestro = json.loads(await websocket.recv())
                if maestro["status"] == STATUS_ALL_DONE:
                    self.status = STATUS_ALL_DONE
                elif maestro["status"] == STATUS_TASK_RECEIVED:
                    self.currenttask = maestro["incoming_task"]
                    self.currenttaskid = self.currenttask["taskid"]
                    self.status = STATUS_TASK_RECEIVED
            ot2 = {"status": self.status, "current_task": self.currenttask["taskid"]}
            await websocket.send(json.dumps(ot2))

    async def process_task(self):
        if self.status == STATUS_TASK_RECEIVED:
            self.status = STATUS_TASK_INPROGRESS
            function = self.tasklist[self.currenttask["function"]]
            await function(*self.currenttask["args"], **self.currenttask["kwargs"])
            self.status = STATUS_IDLE
        # return True  # flag to indicate whether experiment is completed

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
        protocol_context.load_labware("sartorius_safetyspace_tiprack_200ul", slot=slot)
        for slot in ["8"]
    ]

    # note that each stock tray name must match the names from experiment designer!
    stocks = {
        "StockTray1": protocol_context.load_labware(
            "frg_12_wellplate_15000ul", slot="9"
        )
    }

    empty_wells_for_dummy_moves = [
        stocks["StockTray1"]["B2"],
    ]

    listener = Listener(
        protocol_context=protocol_context,
        tips=tips,
        stocks=stocks,
        spincoater=protocol_context.load_labware("frg_spincoater_v1", slot="3"),
    )

    # each piece of labware has to be involved in some dummy moves to be included in protocol
    # we "aspirate" from 10mm above the top of first well on each labware to get it into the protocol
    for side, p in listener.pipettes.items():
        p.pick_up_tip()
        volume = 0
        for name, labware in stocks.items():
            p.aspirate(10, labware["A1"].top(10))
            volume += 10
        p.dispense(volume, listener.spincoater["Chuck"])
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
