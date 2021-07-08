import asyncio
import websockets
import json
import time
import ntplib
from threading import Thread

# import nest_asyncio

# nest_asyncio.apply()

# status enumerations
STATUS_IDLE = 0
STATUS_TASK_RECEIVED = 1
STATUS_TASK_INPROGRESS = 2
# STATUS_TASK_COMPLETE = 3
STATUS_ALL_DONE = 9


# class ListenerWebsocket:
#     def __init__(
#         self,
#         protocol_context,
#         tips,
#         stocks,
#         mixing,
#         spincoater,
#         ip="0.0.0.0",
#         port=8764,
#     ):
#         ## Server constants
#         self.ip = ip
#         self.port = port
#         self.q = asyncio.PriorityQueue()
#         self._worker = asyncio.create_task(self.worker())
#         # self.localloop = asyncio.new_event_loop()
#         # self.localloop.run_forever()
#         # self._start_worker_thread()  # creates self.loop, self._worker

#         ## Task constants
#         self.completed_tasks = {}
#         self.status = STATUS_IDLE
#         self.tips = tips
#         self.stocks = stocks
#         self.mixing = mixing  # TODO intermediate mixing wells
#         self._sources = {**self.stocks, **self.mixing}

#         self.spincoater = spincoater
#         self.CHUCK = "A1"
#         self.STANDBY = "B1"

#         self.pipettes = {
#             side: protocol_context.load_instrument(
#                 "p300_single_gen2", side, tip_racks=self.tips
#             )
#             for side in ["left", "right"]
#         }
#         self.AIRGAP = 20  # airgap, in ul, to aspirate after solution. helps avoid drips, but reduces max tip capacity
#         self.DISPENSE_HEIGHT = (
#             1  # mm, distance between tip and bottom of wells while dispensing
#         )
#         self.DISPENSE_RATE = 10  # uL/s
#         self.SPINCOATING_DISPENSE_HEIGHT = 6  # mm, distance between tip and chuck
#         self.SPINCOATING_DISPENSE_RATE = 50  # uL/s
#         self.SLOW_Z_RATE = 20  # mm/s

#         self.ANTISOLVENT_PIPETTE = self.pipettes[
#             "left"
#         ]  # default left pipette for antisolvent
#         self.PSK_PIPETTE = self.pipettes["right"]  # default right for psk

#         self.__calibrate_time_to_nist()
#         self.tasks = {
#             "aspirate_for_spincoating": self.aspirate_for_spincoating,
#             "aspirate_both_for_spincoating": self.aspirate_both_for_spincoating,
#             "dispense_onto_chuck": self.dispense_onto_chuck,
#             "stage_for_dispense": self.stage_for_dispense,
#             "cleanup": self.cleanup,
#         }

#     ### Time Synchronization with NIST

#     def __calibrate_time_to_nist(self):
#         client = ntplib.NTPClient()
#         response = None
#         while response is None:
#             try:
#                 response = client.request("europe.pool.ntp.org", version=3)
#             except:
#                 pass
#         t_local = time.time()
#         self.__local_nist_offset = response.tx_time - t_local

#     def nist_time(self):
#         return time.time() + self.__local_nist_offset

#     ### Server Methods
#     def start(self):
#         loop = asyncio.get_event_loop()
#         _start_server = websockets.serve(self.main, self.ip, self.port)
#         loop.run_until_complete(_start_server)

#     async def process_task(self, task, websocket):
#         # print(f"> received new task {task['taskid']}")
#         time = task.pop("nist_time")
#         ot2 = {"acknowledged": task["taskid"]}
#         await self.q.put((time, task))
#         await websocket.send(json.dumps(ot2))

#     async def update_status(self, websocket):
#         # print("> updating task status")
#         ot2 = {"completed": self.completed_tasks}
#         await websocket.send(json.dumps(ot2))
#         self.completed_tasks = {}

#     async def main(self, websocket, path):
#         finished = False
#         while not finished:
#             maestro = json.loads(await websocket.recv())
#             if "task" in maestro:
#                 await self.process_task(maestro["task"], websocket)
#             if "status" in maestro or len(self.completed_tasks) > 0:
#                 await self.update_status(websocket)
#             if "complete" in maestro:
#                 finished = True
#                 # self.__stop.set()  # flag the websocket to close
#                 self.status = STATUS_ALL_DONE

#     async def worker(self):
#         while True:
#             # Get a "work item" out of the queue.
#             execution_time, task = await self.q.get()
#             self.status = STATUS_TASK_RECEIVED
#             sleep_for = execution_time - self.nist_time()
#             if sleep_for > 0:
#                 await asyncio.sleep(sleep_for)
#             self.status = STATUS_TASK_INPROGRESS
#             self.tasks[task["task"]](*task["args"], **task["kwargs"])
#             # Notify the queue that the "work item" has been processed.
#             self.q.task_done()
#             self.status = STATUS_IDLE

#             self.completed_tasks[task["taskid"]] = self.nist_time()
#             print(f"{task['taskid']} ({task['task']}) finished")

#     ### Helper Methods
#     def _parse_pipette(self, pipette):
#         if type(pipette) is int:
#             return self.pipettes[pipette]

#         if type(pipette) is str:
#             pipette = pipette.lower()
#         if pipette in ["psk", "perovskite", "p", "left", "l"]:
#             return self.PSK_PIPETTE
#         elif pipette in ["as", "antisolvent", "a", "right", "r"]:
#             return self.ANTISOLVENT_PIPETTE
#         else:
#             raise ValueError("Invalid pipette name given!")

#     def _aspirate_from_well(
#         self, tray, well, volume, pipette, slow_retract, air_gap, touch_tip
#     ):
#         p = pipette
#         p.move_to(self._sources[tray][well].bottom(p.well_bottom_clearance.aspirate))
#         p.aspirate(volume)
#         if slow_retract:
#             p.move_to(self._sources[tray][well].top(2), speed=self.SLOW_Z_RATE)
#         if air_gap:
#             p.air_gap(self.AIRGAP)
#         if touch_tip:
#             p.touch_tip()

#     ### Callable Tasks

#     def aspirate_for_spincoating(
#         self,
#         tray,
#         well,
#         volume,
#         pipette="right",
#         slow_retract=True,
#         air_gap=True,
#         touch_tip=True,
#     ):
#         """Aspirates from a single source well and stages the pipette near the spincoater"""
#         p = self._parse_pipette(pipette=pipette)
#         if p.has_tip:
#             p.drop_tip()
#         p.pick_up_tip()
#         self._aspirate_from_well(
#             tray=tray,
#             well=well,
#             volume=volume,
#             pipette=p,
#             slow_retract=slow_retract,
#             air_gap=air_gap,
#             touch_tip=touch_tip,
#         )
#         self.stage_for_dispense(pipette=pipette)

#     def aspirate_both_for_spincoating(
#         self,
#         psk_tray,
#         psk_well,
#         psk_volume,
#         as_tray,
#         as_well,
#         as_volume,
#         slow_retract=True,
#         air_gap=True,
#         touch_tip=True,
#     ):
#         """Aspirates two solutions and stages the perovskite (right) pipette near spincoater"""
#         for p in self.pipettes.values():
#             if p.has_tip:
#                 p.drop_tip
#         for p in self.pipettes.values():
#             p.pick_up_tip()

#         self._aspirate_from_well(
#             tray=psk_tray,
#             well=psk_well,
#             volume=psk_volume,
#             pipette=self.PSK_PIPETTE,
#             slow_retract=slow_retract,
#             air_gap=air_gap,
#             touch_tip=touch_tip,
#         )
#         self._aspirate_from_well(
#             tray=as_tray,
#             well=as_well,
#             volume=as_volume,
#             pipette=self.ANTISOLVENT_PIPETTE,
#             slow_retract=slow_retract,
#             air_gap=air_gap,
#             touch_tip=touch_tip,
#         )

#         self.stage_for_dispense(pipette="perovskite")

#     def stage_for_dispense(self, pipette):
#         p = self.parse_pipette(pipette)
#         p.moveto(self.spincoater[self.STANDBY].top())

#     def dispense_onto_chuck(self, pipette, height=None, rate=None):
#         """dispenses contents of declared pipette onto the spincoater"""
#         if height is None:
#             height = self.SPINCOATING_DISPENSE_HEIGHT
#         elif height < 0:
#             height = 0  # negative height = crash into substrate!
#         if rate is None:
#             rate = self.SPINCOATING_DISPENSE_RATE

#         p = self.parse_pipette(pipette)
#         # p = self.pipettes["left"]
#         # relative_rate = rate / p.flow_rate
#         relative_rate = 1
#         # p.move_to(self.spincoater[self.CHUCK].top(height))
#         p.dispense(location=self.spincoater[self.CHUCK].top(height), rate=relative_rate)
#         p.blow_out()

#     def cleanup(self):
#         """drops tips of all pipettes into trash to prepare pipettes for future commands"""
#         for p in self.pipettes:
#             p.drop_tip()
#         # for p in self.pipettes:
#         #     p.pick_up_tip()


class ListenerWebsocket:
    def __init__(
        self,
        protocol_context,
        tips,
        stocks,
        mixing,
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
        self.completed_tasks = {}
        self.status = STATUS_IDLE
        self.tips = tips
        self.stocks = stocks
        self.mixing = mixing  # TODO intermediate mixing wells
        self._sources = {**self.stocks, **self.mixing}

        self.spincoater = spincoater
        self.CHUCK = "A1"
        self.STANDBY = "B1"

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
        t_local = time.time()
        self.__local_nist_offset = response.tx_time - t_local

    def nist_time(self):
        return time.time() + self.__local_nist_offset

    ### Server Methods
    def _start_worker_thread(self):
        def f():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.total())
            # start_server = websockets.serve(self.main, self.ip, self.port)
            # self.loop.run_until_complete(start_server)

        #             self.create_
        #             self.loop.run_until_complete(self._start_server())
        #             self.loop.create_task(self.worker())
        #             self.q = asyncio.PriorityQueue()

        # self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=f, args=())
        self.thread.start()

    async def process_task(self, task, websocket):
        # print(f"> received new task {task['taskid']}")
        time = task.pop("nist_time")
        ot2 = {"acknowledged": task["taskid"]}
        await self.q.put((time, task))
        await websocket.send(json.dumps(ot2))

    async def update_status(self, websocket):
        # print("> updating task status")
        ot2 = {"completed": self.completed_tasks}
        await websocket.send(json.dumps(ot2))
        self.completed_tasks = {}

    async def total(self):
        self.q = asyncio.PriorityQueue()
        await asyncio.gather(self._start_server(), self.worker())

    async def main(self, websocket, path):
        finished = False
        while not finished:
            maestro = json.loads(await websocket.recv())
            if "task" in maestro:
                await self.process_task(maestro["task"], websocket)
            if "status" in maestro or len(self.completed_tasks) > 0:
                await self.update_status(websocket)
            if "complete" in maestro:
                finished = True
                self.__stop.set()  # flag the websocket to close
                self.status = STATUS_ALL_DONE

    async def worker(self):
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

            self.completed_tasks[task["taskid"]] = self.nist_time()
            print(f"{task['taskid']} ({task['task']}) finished")

    async def _start_server(self):
        self.__stop = asyncio.Event()
        async with websockets.serve(self.main, self.ip, self.port):
            await self.__stop.wait()

    def start(self):
        self._start_worker_thread()
        # self.loop = asyncio.new_event_loop()
        # start_server = websockets.serve(self.main, self.ip, self.port)
        # asyncio.get_event_loop().run_until_complete(start_server)
        # asyncio.get_event_loop().run_forever()
        # asyncio.create_task(self.worker())
        # _start_server = websockets.serve(self.main, self.ip, self.port)
        # self.__stop = asyncio.Event()
        # self.loop.create_task(self._start_server())
        # self.loop.call_soon_threadsafe(self._start_server())

    ### Helper Methods
    def _parse_pipette(self, pipette):
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

    def _aspirate_from_well(
        self, tray, well, volume, pipette, slow_retract, air_gap, touch_tip
    ):
        p = pipette
        p.move_to(self._sources[tray][well].bottom(p.well_bottom_clearance.aspirate))
        p.aspirate(volume)
        if slow_retract:
            p.move_to(self._sources[tray][well].top(2), speed=self.SLOW_Z_RATE)
        if air_gap:
            p.air_gap(self.AIRGAP)
        if touch_tip:
            p.touch_tip()

    ### Callable Tasks

    def __initialize_tasks(self):
        self.tasks = {
            "aspirate_for_spincoating": self.aspirate_for_spincoating,
            "aspirate_both_for_spincoating": self.aspirate_both_for_spincoating,
            "dispense_onto_chuck": self.dispense_onto_chuck,
            "stage_for_dispense": self.stage_for_dispense,
            "cleanup": self.cleanup,
        }

    def aspirate_for_spincoating(
        self,
        tray,
        well,
        volume,
        pipette="right",
        slow_retract=True,
        air_gap=True,
        touch_tip=True,
    ):
        """Aspirates from a single source well and stages the pipette near the spincoater"""
        p = self._parse_pipette(pipette=pipette)
        if p.has_tip:
            p.drop_tip()
        p.pick_up_tip()
        self._aspirate_from_well(
            tray=tray,
            well=well,
            volume=volume,
            pipette=p,
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
        )
        self.stage_for_dispense(pipette=pipette)

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
        """Aspirates two solutions and stages the perovskite (right) pipette near spincoater"""
        for p in self.pipettes.values():
            if p.has_tip:
                p.drop_tip
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

        self.stage_for_dispense(pipette="perovskite")

    def stage_for_dispense(self, pipette):
        p = self._parse_pipette(pipette)
        p.moveto(self.spincoater[self.STANDBY].top())

    def dispense_onto_chuck(self, pipette, height=None, rate=None):
        """dispenses contents of declared pipette onto the spincoater"""
        if height is None:
            height = self.SPINCOATING_DISPENSE_HEIGHT
        elif height < 0:
            height = 0  # negative height = crash into substrate!
        if rate is None:
            rate = self.SPINCOATING_DISPENSE_RATE

        p = self.parse_pipette(pipette)
        # p = self.pipettes["left"]
        # relative_rate = rate / p.flow_rate
        relative_rate = 1
        # p.move_to(self.spincoater[self.CHUCK].top(height))
        p.dispense(location=self.spincoater[self.CHUCK].top(height), rate=relative_rate)
        p.blow_out()

    def cleanup(self):
        """drops tips of all pipettes into trash to prepare pipettes for future commands"""
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

    listener = ListenerWebsocket(
        protocol_context=protocol_context,
        tips=tips,
        stocks=stocks,
        mixing=wellplates,
        spincoater=protocol_context.load_labware("frg_spincoater_v1", location="3"),
    )

    # each piece of labware has to be involved in some dummy moves to be included in protocol
    # we "aspirate" from 10mm above the top of first well on each labware to get it into the protocol
    for side, p in listener.pipettes.items():
        for name, labware in {**stocks, **wellplates}.items():
            p.move_to(labware["A1"].top(30))
        p.move_to(listener.spincoater[listener.CHUCK].top(30))
    listener.pipettes["right"].move_to(tips[0]["A1"].top(10))
    # p.pick_up_tip()
    # p.pick_up_tip()
    # volume = 0
    # for name, labware in {**stocks, **wellplates}.items():
    #     p.aspirate(10, labware["A1"].top(10))
    #     volume += 10
    # p.dispense(volume, listener.spincoater[listener.CHUCK])
    # p.return_tip()
    # p.reset_tipracks()

    if protocol_context.is_simulating():  # stop here during simulation
        return

    # listen for instructions from maestro
    listener.start()
    while listener.status != STATUS_ALL_DONE:
        time.sleep(0.2)
