import asyncio
import websockets
import json
import time
import ntplib
from threading import Thread
from opentrons import types

# import nest_asyncio

# nest_asyncio.apply()

# status enumerations
STATUS_IDLE = 0
STATUS_TASK_RECEIVED = 1
STATUS_TASK_INPROGRESS = 2
# STATUS_TASK_COMPLETE = 3
STATUS_ALL_DONE = 9


metadata = {
    "protocolName": "Maestro Listener",
    "author": "Rishi Kumar",
    "source": "FRG",
    "apiLevel": "2.10",
}

mixing_netlist = []


class ListenerWebsocket:
    def __init__(
        self,
        protocol_context,
        tips,
        labwares,
        spincoater,
        ip="0.0.0.0",
        port=8764,
    ):
        ## Server constants
        self.ip = ip
        self.port = port
        # self.localloop = asyncio.new_event_loop()
        # self.localloop.run_forever()
        # self._start_worker_thread()  # creates self.loop, self._worker

        ## Task constants
        self.recently_completed_tasks = {}
        self.all_completed_tasks = {}
        self.status = STATUS_IDLE
        self.tips = tips
        tip_racks = list(self.tips.keys())
        self._sources = labwares
        self.TRASH = protocol_context.fixed_trash["A1"]
        self.spincoater = spincoater
        self.CHUCK = "A1"
        self.STANDBY = "B1"
        self.CLEARCHUCKPOSITION = (
            150,
            100,
            100,
        )  # mm, 0,0,0 = front left floor corner of gantry volume.
        self.AIRGAP = 10  # airgap, in ul, to aspirate after solution. helps avoid drips, but reduces max tip capacity
        self.ASPIRATE_HEIGHT = (
            0.3  # mm, distance between tip and bottom of wells while aspirating
        )
        self.DISPENSE_HEIGHT = (
            1  # mm, distance between tip and bottom of wells while dispensing
        )
        self.DISPENSE_RATE = 150  # uL/s
        self.SPINCOATING_DISPENSE_HEIGHT = 1  # mm, distance between tip and chuck
        self.SPINCOATING_DISPENSE_RATE = 200  # uL/s
        self.SLOW_Z_RATE = 20  # mm/s
        self.SLOW_XY_RATE = 100  # mm/s
        self.MIX_VOLUME = (
            50  # uL to repeatedly aspirate/dispense when mixing well contents
        )

        self.pipettes = {
            side: protocol_context.load_instrument(
                "p300_single_gen2", mount=side, tip_racks=tip_racks
            )
            for side in ["left", "right"]
        }
        for tiprack, unavailable_tips in self.tips.items():
            for tip in unavailable_tips:
                tiprack.use_tips(
                    start_well=tiprack[tip], num_channels=1
                )  # remove these tips from the tip iterator

        for p in self.pipettes.values():
            p.well_bottom_clearance.aspirate = self.ASPIRATE_HEIGHT
            p.well_bottom_clearance.dispense = self.DISPENSE_HEIGHT

        # will be populated with (tray,well):tip coordinate as protocol proceeds
        self.reusable_tips = {}
        self.return_current_tip = {
            p: (False, (None, None))
            for p in self.pipettes.values()  # bool = whether to return, (labware name, well to return to) = key
        }

        self.__calibrate_time_to_nist()
        self.__initialize_tasks()  # populate task list

    ### Time Synchronization with NIST

    def __calibrate_time_to_nist(self):
        client = ntplib.NTPClient()
        response = None
        while response is None:
            try:
                response = client.request("europe.pool.ntp.org", version=3)
            except:
                pass
        self.__local_nist_offset = response.tx_time - time.time()

    def nist_time(self):
        return time.time() + self.__local_nist_offset

    ### Server Methods
    # Running the server
    async def __main(self):
        self.q = asyncio.PriorityQueue()
        await asyncio.gather(self.__start_server(), self.__worker())

    async def __start_server(self):
        self.__stop = asyncio.Event()
        async with websockets.serve(self.__receive_messages, self.ip, self.port):
            await self.__stop.wait()

    async def __receive_messages(self, websocket, path):
        finished = False
        while not finished:
            maestro = json.loads(await websocket.recv())
            if "task" in maestro:
                await self.__process_task(maestro["task"], websocket)
            if "status" in maestro or len(self.recently_completed_tasks) > 0:
                await self.__update_status(websocket)
            if "complete" in maestro:
                finished = True
                self.__stop.set()  # flag the websocket to close
                self.status = STATUS_ALL_DONE

    # Processing tasks
    async def __worker(self):
        while True:
            # Get a "work item" out of the queue.
            execution_time, task = await self.q.get()
            self.status = STATUS_TASK_RECEIVED
            sleep_for = execution_time - self.nist_time()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            self.status = STATUS_TASK_INPROGRESS
            self.tasks[task["task"]](*task["args"], **task["kwargs"])
            # Notify the queue that the "work item" has been processed.
            self.q.task_done()
            self.status = STATUS_IDLE

            self.recently_completed_tasks[task["taskid"]] = self.nist_time()
            self.all_completed_tasks.update(self.recently_completed_tasks)
            task["finished_event"].set()
            # print(f"{task['taskid']} ({task['task']}) finished")

    async def __process_task(self, task, websocket):
        # print(f"> received new task {task['taskid']}")
        time = task.pop("nist_time")
        task["finished_event"] = asyncio.Event()
        await self.q.put((time, task))

        ot2 = {"acknowledged": task["taskid"]}
        await websocket.send(json.dumps(ot2))

        await task["finished_event"].wait()

    async def __update_status(self, websocket):
        # print("> updating task status")
        ot2 = {"completed": self.all_completed_tasks}
        await websocket.send(json.dumps(ot2))
        self.recently_completed_tasks = {}

    # start it all
    def start(self):
        def f():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.__main())

        self.thread = Thread(target=f, args=())
        self.thread.start()

    ### Helper Methods
    def _get_pipette(self, pipette):
        if type(pipette) is int:
            return self.pipettes[pipette]
        if type(pipette) is str:
            pipette = pipette.lower()

        if pipette in ["psk", "perovskite", "p", "right", "r"]:
            return self.pipettes["right"]
        elif pipette in ["as", "antisolvent", "a", "left", "l"]:
            return self.pipettes["left"]
        else:
            raise ValueError("Invalid pipette name given!")

    def _aspirate_from_well(
        self, tray, well, volume, pipette, slow_retract, air_gap, touch_tip, pre_mix
    ):
        p = pipette
        # p.move_to(self._sources[tray][well].bottom(p.well_bottom_clearance.aspirate))
        if pre_mix[0] > 0:
            p.mix(
                repetitions=pre_mix[0],
                volume=pre_mix[1],
                location=self._sources[tray][well],
            )
        p.aspirate(volume=volume, location=self._sources[tray][well])
        if slow_retract:
            p.move_to(self._sources[tray][well].top(2), speed=self.SLOW_Z_RATE)
        if touch_tip:
            p.touch_tip()
        if air_gap:
            relative_rate = 20 / p.flow_rate.dispense  # 20 uL/s
            p.aspirate(
                volume=self.AIRGAP,
                location=self._sources[tray][well].top(2),
                rate=relative_rate,
            )  # force a slow airgap
            # p.air_gap(self.AIRGAP)

    def _next_tip(self):
        for tiprack in self.tips.keys():
            next_tip = tiprack.next_tip(num_tips=1)
            if next_tip is not None:
                break

        if next_tip is None:
            raise Exception("No remaining tips!")
        return next_tip

    def _get_reusable_tip(self, tray, well):
        key = (tray, well)
        if key in self.reusable_tips:
            next_tip = self.reusable_tips[key]
        else:
            next_tip = self._next_tip()
            self.reusable_tips[key] = next_tip
        return next_tip

    ### Callable Tasks

    def __initialize_tasks(self):
        self.tasks = {
            "get_" "aspirate_for_spincoating": self.aspirate,
            "dispense_onto_chuck": self.dispense_onto_chuck,
            "stage_for_dispense": self.stage_for_dispense,
            "clear_chuck": self.clear_chuck,
            "cleanup": self.cleanup,
        }

    def get_tip(self, tray, well, pipette, reuse_tip=False):
        p = self._get_pipette(pipette=pipette)

        if reuse_tip:
            if p.has_tip:
                if self.return_current_tip[p][1] == (
                    tray,
                    well,
                ):  # we already have the correct tip on
                    return
                else:  # put this tip back, get the right one
                    p.return_tip()
                    self.return_current_tip[p] = (False, (None, None))

                    tip = self._get_reusable_tip(tray, well)
                    p.pick_up_tip(tip)
                    self.return_current_tip[p] = (True, (tray, well))
        else:
            if p.has_tip:
                if self.return_current_tip[p][0]:
                    p.return_tip()
                    self.return_current_tip[p] = (False, (None, None))
                else:
                    p.drop_tip()
                p.pick_up_tip()

    def aspirate(
        self,
        tray,
        well,
        volume,
        pipette="perovskite",
        slow_retract=True,
        air_gap=True,
        touch_tip=True,
        pre_mix=(0, 0),
    ):
        """Aspirates from a single source well. Assumes the pipette already has a tip loaded"""
        p = self._get_pipette(pipette=pipette)
        if pre_mix[0] > 0:
            p.mix(
                repetitions=pre_mix[0],
                volume=pre_mix[1],
                location=self._sources[tray][well],
            )
        p.aspirate(volume=volume, location=self._sources[tray][well])
        if slow_retract:
            p.move_to(self._sources[tray][well].top(2), speed=self.SLOW_Z_RATE)
        if touch_tip:
            p.touch_tip()
        if air_gap:
            relative_rate = 20 / p.flow_rate.dispense  # 20 uL/s
            p.aspirate(
                volume=self.AIRGAP,
                location=self._sources[tray][well].top(2),
                rate=relative_rate,
            )  # force a slow airgap

    def stage_for_dispense(self, pipette, slow_travel=False):
        p = self._get_pipette(pipette)
        if slow_travel:
            speed = self.SLOW_XY_RATE
        else:
            speed = None
        p.move_to(self.spincoater[self.STANDBY].top(), speed=speed)

    def dispense_onto_chuck(self, pipette, **kwargs):  # , height=None, rate=None):
        """dispenses contents of declared pipette onto the spincoater"""
        height = kwargs.get("height", self.SPINCOATING_DISPENSE_HEIGHT)
        rate = kwargs.get("rate", self.SPINCOATING_DISPENSE_RATE)
        slow_travel = kwargs.get("slow_travel", False)
        blow_out = kwargs.get("blow_out", False)

        p = self._get_pipette(pipette)
        relative_rate = rate / p.flow_rate.dispense
        if slow_travel:
            p.move_to(
                location=self.spincoater[self.CHUCK].top(height),
                speed=self.SLOW_XY_RATE,
            )
        p.dispense(location=self.spincoater[self.CHUCK].top(height), rate=relative_rate)
        if blow_out:
            p.blow_out()

    def clear_chuck(self):
        self.pipettes["right"].move_to(
            location=types.Location(
                point=types.Point(*self.CLEARCHUCKPOSITION), labware=None
            )
        )

    def mix(self, dispense_instructions):
        p = self._get_pipette(pipette="perovskite")
        for dispense in dispense_instructions:
            tray = dispense["tray"]
            well = dispense["well"]
            source_well = self._sources[tray][well]

            destination_wells = []
            volumes = []
            for d in dispense["destinations"]:
                tray = d["tray"]
                for well, volume in zip(d["wells"], d["volumes"]):
                    destination_wells.append(self._sources[tray][well])
                    volumes.append(volume)

            p.distribute(
                volumes,
                source_well,
                destination_wells,
                touch_tip=False,
                blow_out=True,
                disposal_volume=0,
            )

    def cleanup(self):
        """drops/returns tips of all pipettes to prepare pipettes for future commands

        the order of operations feels overly complicated, but is chosen to minimize
        the travel (both horizontally and vertically) of the pipette heads
        """
        # drop all tips that dont need to be returned
        for p, return_this_tip in self.return_current_tip.items():
            if not p.has_tip:
                continue
            if not return_this_tip:
                p.drop_tip()

        # first blow out all returning, but leave them on - will be swapped out on next spincoat if they need to change
        for p, return_this_tip in self.return_current_tip.items():
            if return_this_tip:
                p.blow_out(self.TRASH)
        # for p, return_this_tip in self.return_current_tip.items():
        #     if return_this_tip:
        #         p.return_tip()
        #         self.return_current_tip[p] = False

        p = self._get_pipette("perovskite")
        if not p.has_tip:  # if the first pipette is clear, stage it ready to pick up
            next_tip = self._next_tip()
            p.move_to(next_tip.top(5))

    def final_cleanup(self):
        # drop any currently mounted tips
        for p in self.pipettes.values():
            if p.has_tip:
                p.drop_tip()

        # move all the reused tips into the trash
        for tip in self.reusable_tips.values():
            p.pick_up_tip(tip)
            p.drop_tip()

        # fill tip slot A1 for all racks for calibration of next run
        for tiprack in self.tips.keys():
            # if tiprack.
            pass


def run(protocol_context):
    # define your hardware
    tips = {}
    labwares = {}

    # spincoater
    spincoater = protocol_context.load_labware("frg_spincoater_v1", location="3")

    listener = ListenerWebsocket(
        protocol_context=protocol_context,
        tips=tips,
        labwares=labwares,
        spincoater=spincoater,
    )

    # each piece of labware has to be involved in some dummy moves to be included in protocol
    # we "aspirate" from 10mm above the top of first well on each labware to get it into the protocol
    for side, p in listener.pipettes.items():
        p.move_to(listener.spincoater[listener.CHUCK].top(30))
        for name, labware in labwares.items():
            p.move_to(labware["A1"].top(30))
        for labware in tips:
            p.move_to(labware["A1"].top(30))

    # run through the pre-experiment mixing
    for generation in mixing_netlist:
        for source_str, destination_strings in generation.items():
            source_labware, source_well = source_str.split("-")
            source = labwares[source_labware][source_well]

            destinations = []
            volumes = []
            for destination_str, volume in destination_strings.items():
                destination_labware, destination_well = destination_str.split("-")
                destinations.append(labwares[destination_labware][destination_well])
                volumes.append(volume)

            listener.pipettes["right"].transfer(
                volume=volumes,
                source=source,
                dest=destinations,
                disposal_volume=0,
                carryover=True,
                mix_before=(3, 50),
                new_tip="once",
                blow_out=True,
            )

    if protocol_context.is_simulating():  # stop here during simulation
        return

    # listen for instructions from maestro
    listener.start()
    protocol_context.comment("Waiting for Maestro")
    while listener.status != STATUS_ALL_DONE:
        time.sleep(0.2)
