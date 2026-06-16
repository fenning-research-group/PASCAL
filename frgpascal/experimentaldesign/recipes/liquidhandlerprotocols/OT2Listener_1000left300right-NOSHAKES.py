"""This OT2PASCALProtocol used the following template:
OT2Listener_1000left300right-NOSHAKES.py
File Created At:
"""
import asyncio
import websockets
import json
import time
import socket
import struct
from threading import Thread
from opentrons import types
from dataclasses import asdict
#==Done Importing==
# see: frgpascal.experimentaldesign.protocolwriter.py generate_ot2_protocolNEW()
#==Setup OT2 Motion Config== 
OT2Config = OT2MotionConfig()

# status enumerations
STATUS_IDLE = 0
STATUS_TASK_RECEIVED = 1
STATUS_TASK_INPROGRESS = 2
# STATUS_TASK_COMPLETE = 3
STATUS_ALL_DONE = 9


metadata = {
    "protocolName": "Maestro Listener - Large Volume Pipette on Left, Small Volume Pipette on Right",
    "author": "Rishi Kumar, Deniz Cakan, Jack Palmer, Eric Oberholtz",
    "source": "FRG",
    "apiLevel": "2.10",
}

mixing_netlist = []


class ListenerWebsocket:
    def __init__(
        self,
        protocol_context,
        tips_300,
        tips_1000,
        labwares,
        spincoater,
        config, #==Update Default Config==
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
        self.tips_300 = tips_300
        self.tips_1000 = tips_1000
        tip_racks_300 = list(self.tips_300.keys())
        tip_racks_1000 = list(self.tips_1000.keys())
        self.labwares = labwares
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
        # TODO: Fix slow motion when gantry is updated
        # self.SLOWEST_XY_RATE = 100 # mm/s
        self.SLOWEST_XY_RATE = 20 # mm/s
        self.MIX_VOLUME = (
            50  # uL to repeatedly aspirate/dispense when mixing well contents
        )
        self.config = config #==Add Config to ListenerWebsocket==
        # self._config = config # defined by protocolwriter

        # self.pipettes = {
        #     side: protocol_context.load_instrument(
        #         "p300_single_gen2", mount=side, tip_racks=tip_racks
        #     )
        #     for side in ["left", "right"]
        # }

        self.pipettes = {
            "right": protocol_context.load_instrument(
                "p300_single_gen2", mount="right", tip_racks=tip_racks_300
            ),
            "left": protocol_context.load_instrument(
                "p1000_single_gen2", mount="left", tip_racks=tip_racks_1000
            ),
        }

        # for p in self.pipettes.values():
        #     p.min_volume = 10  # vs 20 stock
        self.set_starting_tips()

        for p in self.pipettes.values():
            p.well_bottom_clearance.aspirate = self.ASPIRATE_HEIGHT
            p.well_bottom_clearance.dispense = self.DISPENSE_HEIGHT

        # will be populated with (tray,well):tip coordinate as protocol proceeds
        self.reusable_tips = {}
        self.return_current_tip = {p: False for p in self.pipettes.values()}

        self.__calibrate_time_to_nist()
        self.__initialize_tasks()  # populate task list
        self._NEVER_SAVED = True
        
        self.__save_defaults()
        self._protocol_context = protocol_context
        self._HW_API = self._protocol_context._implementation.get_hardware()
        # #TODO: uncomment this for eliminating opentrons shaking
        # ## must also account for new <spincoat> spin_start delay time as speeds decrease
        # new_speed = self.SLOWEST_XY_RATE
        # protocol_context.max_speeds["X"] = new_speed
        # protocol_context.max_speeds["Y"] = new_speed

    # ==Define Config Property==

    ### Time Synchronization with NIST

    def __calibrate_time_to_nist(self):
        def get_ntp_time(ntp_server="europe.pool.ntp.org"):
            ntp_packet = b'\x1b' + 47 * b'\0'  # NTP request packet
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(5)
                s.sendto(ntp_packet, (ntp_server, 123))
                data, _ = s.recvfrom(1024)
            unpacked_data = struct.unpack("!12I", data)
            time_since_1900 = unpacked_data[10]
            return time_since_1900 - 2208988800  # Convert to Unix epoch (1970)

        response_time = None
        while response_time is None:
            try:
                response_time = get_ntp_time()
            except Exception:
                pass  # Retry if there's an issue connecting to the NTP server

        self.__local_nist_offset = response_time - time.time()

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
            # if "print_sample" in maestro:
                # self._protocol_context.comment(maestro["print_sample"])

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

    def set_starting_tips(self):
        for p in self.pipettes.values():
            p.reset_tipracks()
        for tiprack, unavailable_tips in {**self.tips_1000, **self.tips_300}.items():
            for tip in unavailable_tips:
                tiprack.use_tips(
                    start_well=tiprack[tip], num_channels=1
                )  # remove these tips from the tip iterator

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
    
    def _smooth_touch_tip(self, well, pipette, speed, radius_frac = 1):
        """Mirrors the InstrumentContext.touch_tip() execution, with finer control of speed.

        Parameters
        ----------
        well : WellContext
            the Well object representing the liquid storage slot.
        pipette : InstrumentContext
            the pipette object
        speed : float
            motion speed along all axes, in mm/s
        radius_frac : int, optional
            % of the well radius we move the pipette, by default 1.
            Can decrease if solutions are particularly sticky to ~0.85
        """
        p = pipette
        center_location = well.top()
        center_point = center_location.point
        if hasattr(well, 'diameter') and well.diameter is not None:
            r_x = (well.diameter / 2.0) * radius_frac
            r_y = r_x
        else: # non-circular well!
            r_x = (well.length / 2.0) * radius_frac
            r_y = (well.width / 2.0) * radius_frac
        edge_points = [
            types.Point(
                center_point.x + r_x, 
                center_point.y, 
                center_point.z
            ), # East
            types.Point(
                center_point.x - r_x, 
                center_point.y, 
                center_point.z
            ), # West
            types.Point(
                center_point.x,
                center_point.y,
                center_point.z
            ), # middle of vial top
            types.Point(
                center_point.x, 
                center_point.y + r_y, 
                center_point.z
            ), # South
            types.Point(
                center_point.x, 
                center_point.y - r_y, 
                center_point.z
            ), # North
            types.Point(
                center_point.x,
                center_point.y,
                center_point.z
            ), # middle of vial top
        ]
        p.move_to(center_location, speed = speed)
        for edge, direc in zip(edge_points, ["E", "W", "M", "S", "N", "M"]):
            self._protocol_context.comment(f"Moving {direc}")
            p.move_to(center_location.move(edge - center_location.point), speed = speed)
        # p.move_to(center_location, speed = speed)


    def _aspirate_from_well(
        self, tray, well, volume, pipette, slow_retract, air_gap, touch_tip, pre_mix
    ):
        self._protocol_context.comment('START `_aspirate_from_well` step')
        p = pipette
        # p.move_to(self.labwares[tray][well].bottom(p.well_bottom_clearance.aspirate))
        if pre_mix[0] > 0:
            p.mix(
                repetitions=pre_mix[0],
                volume=pre_mix[1],
                location=self.labwares[tray][well],
            )
        p.aspirate(volume=volume, location=self.labwares[tray][well])
        if slow_retract:
            p.move_to(
                self.labwares[tray][well].top(2), 
                speed = self.config.SLOW_Z_RATE,
                # speed=self.SLOW_Z_RATE
            )
        if touch_tip:
            
            self._protocol_context.comment('START `p.touch_tip` step')
            # p.touch_tip(
                # speed = 1 # mm/s
                # speed = self.config.TOUCH_TIP_RATE
            # )
            self._smooth_touch_tip(well = self.labwares[tray][well], pipette = p, speed = self.config.TOUCH_TIP_RATE, radius_frac = 1)
            self._protocol_context.comment('END `p.touch_tip` step')
            # self._protocol_context.comment('START `move out of vial` step')
            # p.moveto(
            #     self.labwares[tray][well].top(2), 
            #     speed = self.config.SLOW_Z_RATE,
            #     # speed = self.SLOW_Z_RATE
            # )
            # self._protocol_context.comment('END `move out of vial` step')
        if air_gap:
            
            self._protocol_context.comment('START `air_gap` step')
            relative_rate = 20 / p.flow_rate.dispense  # 20 uL/s
            p.aspirate(
                volume=self.AIRGAP,
                location=self.labwares[tray][well].top(2),
                rate=relative_rate,
            )  # force a slow airgap
            # p.air_gap(self.AIRGAP)
            
            self._protocol_context.comment('END `air_gap` step')
        self._protocol_context.comment('END `_aspirate_from_well` step')

    def _next_tip(self, pipette):
        pipette = self._get_pipette(pipette)
        if pipette == self.pipettes["right"]:
            tips = self.tips_300
        else:
            tips = self.tips_1000

        for tiprack in tips.keys():
            next_tip = tiprack.next_tip(num_tips=1)
            if next_tip is not None:
                break
        if next_tip is None:
            raise Exception("No remaining tips!")
        return next_tip

    def _get_reusable_tip(self, pipette, tray, well):
        key = (pipette, tray, well)
        if key in self.reusable_tips:
            next_tip = self.reusable_tips[key]
        else:
            next_tip = self._next_tip(pipette)
            self.reusable_tips[key] = next_tip
        return next_tip

    def _load_pipettes(self, psk_tray, psk_well, as_tray, as_well, reuse_psk = False, reuse_as = True):
        p_psk = self.pipettes['right']
        p_as = self.pipettes['left']
        if p_psk.has_tip:
            p_psk.move_to(
                self.TRASH.top(5), 
                speed = self.config.SLOWEST_XY_RATE
                # speed = self.SLOWEST_XY_RATE
            )
            p_psk.drop_tip()
        if p_as.has_tip:
            p_psk.move_to(
                self.TRASH.top(5), 
                speed = self.config.SLOWEST_XY_RATE
                # speed = self.SLOWEST_XY_RATE
            )
            p_as.drop_tip()
        if reuse_psk:
            tip = self._get_reusable_tip(p_psk, psk_tray, psk_well)
            p_psk.move_to(
                tip.top(30), 
                speed = self.config.SLOWEST_XY_RATE
                # speed = self.SLOWEST_XY_RATE
            )
            p_psk.pick_up_tip(tip)
        elif not reuse_psk:
            tip = self._next_tip(pipette = p_psk)
            p_psk.move_to(
                tip.top(30), 
                speed = self.config.SLOWEST_XY_RATE
                # speed = self.SLOWEST_XY_RATE
            )
            p_psk.pick_up_tip(tip)
        if reuse_as:
            tip = self._get_reusable_tip(p_as, as_tray, as_well)
            p_psk.move_to(
                tip.top(30), 
                speed = self.config.SLOWEST_XY_RATE
                # speed = self.SLOWEST_XY_RATE
            )
            p_as.pick_up_tip(tip)
        elif not reuse_as:
            tip = self._next_tip(pipette = p_as)
            p_psk.move_to(
                tip.top(30),
                speed = self.config.SLOWEST_XY_RATE
                # speed = self.SLOWEST_XY_RATE
            )
            p_as.pick_up_tip(tip)
    
    def __save_defaults(self):
        if self._NEVER_SAVED:
            self._defaults = asdict(self.config)
            self._NEVER_SAVED = False
        else:
            raise Exception("Why are we overwriting the hardwareconstants default values? This method should never be directly called by the user.")
    
    def __update_config(self, new_config_dict):
        for k, v in new_config_dict.items():
            if isinstance(v, dict):
                if "acceleration" in k:
                    obj_ = self.config.accelerations
                elif "velocities" in k:
                    obj_ = self.config.velocities
                for k_, v_ in v.items():
                    setattr(
                        obj_, # obj to edit
                        k_, # attr name
                        v_ # new value
                    )
            else:
                setattr(
                    self.config, # obj to edit
                    k, # attr name
                    v # new value
                )

    def _reset_to_defaults(self):
        self.__update_config(
            new_config_dict = self._defaults
        )
    
    def _update_motion(
            self,
            new_config_dict,
        ):
        self._protocol_context.comment("START `update` step")
        old_vX = self.config.velocities.X
        planned_vX = new_config_dict["velocities"]["X"]
        self.__update_config(
            new_config_dict = new_config_dict
        )
        new_vX = self.config.velocities.X
        self._protocol_context.comment(f"END `update` step: old {old_vX};planned {planned_vX};actual {new_vX}")
    
    ### Callable Tasks

    def __initialize_tasks(self):
        self.tasks = {
            "aspirate_for_spincoating": self.aspirate_for_spincoating,
            "aspirate_both_for_spincoating": self.aspirate_both_for_spincoating,
            "dispense_onto_chuck": self.dispense_onto_chuck,
            "stage_for_dispense": self.stage_for_dispense,
            "clear_chuck": self.clear_chuck,
            "cleanup": self.cleanup,
            "mix": self.mix,
            "overwrite_constants": self.overwrite_constants,
            "revert_to_defaults": self.revert_to_defaults,
        }

    def aspirate_for_spincoating(
        self,
        tray,
        well,
        volume,
        pipette="perovskite",
        slow_retract=True,
        air_gap=True,
        touch_tip=True,
        pre_mix=(0, 0),
        reuse_tip=False,
        ot2_settings = {},
    ):
        """Aspirates from a single source well and stages the pipette near the spincoater"""
        # try:
        #     self._update_motion(
        #         new_config_dict = ot2_settings
        #     )
        self._protocol_context.comment('START `aspirate_for_spincoating` step')
        p = self._get_pipette(pipette=pipette)
        self._protocol_context.comment(f'Got the pipette: {p}')
        if reuse_tip:
            self._protocol_context.comment('Reusing tip!')
            tip = self._get_reusable_tip(pipette, tray, well)
            self._protocol_context.comment(f'Next Tip is {type(tip)}')
            if p.has_tip:
                p.move_to(
                    tip.top(10), 
                    speed = self.config.SLOWEST_XY_RATE
                    # speed = self.SLOWEST_XY_RATE
                )
                p.drop_tip()
            p.move_to(
                tip.top(10),
                speed = self.config.SLOWEST_XY_RATE
                # speed = self.SLOWEST_XY_RATE
            )
            p.pick_up_tip(tip)
            self.return_current_tip[p] = True
        else:
            if p.has_tip:
                self._protocol_context.commment('p300 has a tip!')
                p.move_to(
                    self.TRASH['A1'].top(5), 
                    speed = self.config.SLOWEST_XY_RATE
                    # speed = self.SLOWEST_XY_RATE
                )
                p.drop_tip()
            self._protocol_context.comment('thinking about next tip')
            tip = self._next_tip(pipette)
            self._protocol_context.comment('Found next tip')
            self._protocol_context.comment(f'Next Tip is {type(tip)}')
            self._protocol_context.comment(f'Next Tip pos is {tip.top()}')
            p.move_to(
                tip.top(10), 
                speed = self.config.SLOWEST_XY_RATE
                # speed = self.SLOWEST_XY_RATE
            )
            p.pick_up_tip()
        self._aspirate_from_well(
            tray=tray,
            well=well,
            volume=volume,
            pipette=p,
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
            pre_mix=pre_mix,
        )
        # self._protocol_context.comment('END `aspirate_for_spincoating` step')
        # finally:
        #     self._reset_to_defaults()

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
        pre_mix=0,
        legacy = False,
        reuse_as = True,
        reuse_psk = False,
        ot2_settings = {},
    ):
        """Aspirates two solutions and stages the perovskite (right) pipette near spincoater"""
        # try:
        #     self._update_motion(
        #         new_config_dict = ot2_settings
        #     )
        self._protocol_context.comment('START `aspirate_both_for_spincoating` step')
        if legacy:
            for p in self.pipettes.values():
                if p.has_tip:
                    p.drop_tip
            for p in self.pipettes.values():
                p.pick_up_tip() # Opentrons API forces all of the first-called pipette process to be done before moving on to pipette # 2
        else:
            self._load_pipettes(
                psk_tray = psk_tray,
                psk_well = psk_well,
                as_tray = as_tray,
                as_well = as_well,
                reuse_as = reuse_as,
                reuse_psk = reuse_psk
            )

        self._aspirate_from_well(
            tray=psk_tray,
            well=psk_well,
            volume=psk_volume,
            pipette=self._get_pipette("perovskite"),
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
        )
        self._aspirate_from_well(
            tray=as_tray,
            well=as_well,
            volume=as_volume,
            pipette=self._get_pipette("antisolvent"),
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
        )

        self.stage_for_dispense(pipette="perovskite")
        self._protocol_context.comment('END `aspirate_both_for_spincoating` step')
        # finally:
        #     self._reset_to_defaults()

    def stage_for_dispense(self, pipette, slow_travel=False, ot2_settings = {}):
        # try:
        #     self._update_motion(
        #         new_config_dict = ot2_settings,
        #     )
        self._protocol_context.comment('START `stage_for_dispense` step')
        p = self._get_pipette(pipette)
        if slow_travel:
            speed = self.SLOW_XY_RATE
        else:
            speed = None
        # p.move_to(self.spincoater[self.STANDBY].top(), speed=speed)
        p.move_to(self.spincoater[self.STANDBY].top(), speed = self.SLOWEST_XY_RATE)
        self._protocol_context.comment('END `stage_for_dispense` step')
        # finally:
        #     self._reset_to_defaults()

    def dispense_onto_chuck(self, pipette, ot2_settings = {}, **kwargs):  # , height=None, rate=None):
        """dispenses contents of declared pipette onto the spincoater"""
        # try:
        #     self._update_motion(
        #         new_config_dict = ot2_settings
        #         )
        height = kwargs.get("height", self.SPINCOATING_DISPENSE_HEIGHT)
        rate = kwargs.get("rate", self.SPINCOATING_DISPENSE_RATE)
        slow_travel = kwargs.get("slow_travel", False)
        blow_out = kwargs.get("blow_out", False)
        self._protocol_context.comment('START `dispense_onto_chuck` step')
        p = self._get_pipette(pipette)
        relative_rate = rate / p.flow_rate.dispense
        if slow_travel:
            p.move_to(
                location=self.spincoater[self.CHUCK].top(height),
                # speed=self.SLOW_XY_RATE,
                speed = self.SLOWEST_XY_RATE,
            )
        p.dispense(location=self.spincoater[self.CHUCK].top(height), rate=relative_rate)
        if blow_out:
            p.blow_out()
        p.move_to(
            self.spincoater[self.STANDBY].top(), force_direct=True,
            speed = self.SLOWEST_XY_RATE,
        )  # Move off of chuck to prevent dripping onto substrate
        self._protocol_context.comment('END `dispense_onto_chuck` step')
        # finally:
        #     self._reset_to_defaults()

    def clear_chuck(self, ot2_settings = {}):
        # try:
        #     self._update_motion(
        #         new_config_dict = ot2_settings
        #     )
        self._protocol_context.comment('START `clear_chuck` step')
        self.pipettes["right"].move_to(
            location=types.Location(
                point=types.Point(*self.CLEARCHUCKPOSITION), labware=None
            ),
            speed = self.SLOWEST_XY_RATE,
        )
        self._protocol_context.comment('END `clear_chuck` step')
        # finally:
        #     self._reset_to_defaults()

    def mix(self, mixing_netlist, ot2_settings, **kwargs):
        # try:
        #     self._update_motion(
        #         new_config_dict = ot2_settings
        #     )
        p = self._get_pipette(pipette="perovskite")
        for i, (source_str, destination_strings) in enumerate(mixing_netlist.items()):
            source_labware, source_well = source_str.split("-")
            source = self.labwares[source_labware][source_well]

            destinations = []
            volumes = []
            for destination_str, volume in destination_strings.items():
                destination_labware, destination_well = destination_str.split("-")
                destinations.append(
                    self.labwares[destination_labware][destination_well]
                )
                volumes.append(volume)

            if i == len(mixing_netlist) - 1:  # ie this is the last transfer
                mix_after = (5, 50)
            else:
                mix_after = (0, 0)
            dispense_rate0 = p.flow_rate.dispense
            aspirate_rate0 = p.flow_rate.aspirate

            p.flow_rate.aspirate = 20
            p.flow_rate.dispense = 50  # slow to handle viscous solutions

            p.transfer(
                volume=volumes,
                source=source,
                dest=destinations,
                mix_after=mix_after,
                disposal_volume=0,
                carryover=True,
                new_tip="always",
                touch_tip=True,
                blow_out=True,
                blow_out_location="destination well",
                air_gap=20,
            )
            p.flow_rate.aspirate = aspirate_rate0
            p.flow_rate.dispense = dispense_rate0
        # finally:
        #     self._reset_to_defaults()

    def cleanup(self, ot2_settings = {}):
        """drops/returns tips of all pipettes to prepare pipettes for future commands

        the order of operations feels overly complicated, but is chosen to minimize
        the travel (both horizontally and vertically) of the pipette heads
        """
        # try:
        #     self._update_motion(
        #         new_config_dict = ot2_settings
        #     )
        # self._protocol_context.comment("START `cleanup` step")
        # drop all tips that dont need to be returned
        for p, return_this_tip in self.return_current_tip.items():
            if not p.has_tip:
                continue
            if not return_this_tip:
                p.drop_tip()

        # first blow out all returning tips, then drop them back
        for p, return_this_tip in self.return_current_tip.items():
            if return_this_tip:
                p.blow_out(self.TRASH)
        for p, return_this_tip in self.return_current_tip.items():
            if return_this_tip:
                p.return_tip()
                self.return_current_tip[p] = False

        next_tip = self._next_tip(pipette="right")
        p = self._get_pipette("right")
        p.move_to(next_tip.top(5), speed = self.SLOWEST_XY_RATE)
        # self._protocol_context.comment("END `cleanup` step")
        # finally:
        #     self._reset_to_defaults()

    def overwrite_constants(self, ot2_settings = {}):
        """Updates the motion behavior of OT-2 for this particular sample's Worker_SpincoaterLiquidHandler task execution."""
        self._protocol_context.comment("START `overwrite_constants` step")
        # Update the OT2MotionConfig:
        self._update_motion(
            new_config_dict = ot2_settings
        )
        # overwrite the OT-2's default accelerations and max velocities
        orig_hw_config = self._HW_API.config
        new = {
            "acceleration": asdict(self.config.accelerations),
            "default_max_speed": asdict(self.config.velocities),
        }
        orig_hw_config.acceleration = new["acceleration"]
        orig_hw_config.default_max_speed = new["default_max_speed"]
        self._HW_API.set_config(orig_hw_config)
        self._protocol_context.comment("END `overwrite_constants` step")
        

    def revert_to_defaults(self):
        """Resets the motion behavior of OT-2 to legacy settings, to be used at the end of each task execution."""
        self._protocol_context.comment("START `revert_to_defaults` step")
        # Update the OT2MotionConfig:
        self._reset_to_defaults()
        # Apply the saved defaults to the hardware API's default settings again.
        # These get auto-reset when the OT-2 is power cycled, but editing in the code ensures consistent state when not power-cycled post-run.
        orig_hw_config = self._HW_API.config
        new = {
            "acceleration": asdict(self.config.accelerations),
            "default_max_speed": asdict(self.config.velocities),
        }
        orig_hw_config.acceleration = new["acceleration"]
        orig_hw_config.default_max_speed = new["default_max_speed"]
        self._HW_API.set_config(orig_hw_config)
        self._protocol_context.comment("END `revert_to_defaults` step")
        

def run(protocol_context):
    protocol_context.set_rail_lights(on=False)
    # define your hardware

    tips_300 = {}
    tips_1000 = {}

    labwares = {}

    # spincoater
    spincoater = protocol_context.load_labware("frg_spincoater_v1", location="3")
    # Before we define any instruments, access the hardware controller bridge
    # For API 2.10, we can use the internal implementation to get the hardware API
    hw_api = protocol_context._implementation.get_hardware()

    protocol_context.comment("Legacy Hardware Configuration:")
    hw_api = protocol_context._implementation.get_hardware()
    orig_config = hw_api.config
    protocol_context.comment(f"Config Type: {type(orig_config)}")
    protocol_context.comment(f"Config Attributes: {dir(orig_config)}")
    accel = ",".join([f"{k},{v}" for k, v in orig_config.acceleration.items()])
    # jerk = orig_config.junction_deviation
    # protocol_context.comment(f"config keys: {orig_config.keys()}")
    # protocol_context.comment(f"Default speeds: {protocol_context.default_max_speed}")
    # protocol_context.comment(f"Default Y speeds: {protocol_context.max_speeds['Y']}")
    protocol_context.comment(f"O.G. Accel (mm/s^2): {accel}")
    # Define safer acceleration and jerk (junction deviation) values
    # Junction deviation (jerk) default is 0.02. Dropping to 0.01 makes the corners smoother
    new = {
        "acceleration": {
            "X": 1, # 5 too high
            "Y": 1, # 5 too high
            "Z": 100,
            "A": 100,   # Right pipette mount
            "B": 100,   # Left pipette mount
        },
        # "junction_deviation": 0.01,
        "default_max_speed": {
            "X": 50, # 100 too high
            "Y": 50, # 100 too high
            "Z": 125,
            "A": 100,
            "B": 100,
            "C": 100
        }
    }
    orig_config.acceleration = new["acceleration"]
    orig_config.default_max_speed = new["default_max_speed"]
    hw_api.set_config(orig_config)
    new_config = hw_api.config
    # new_config = hw_api.config._replace(acceleration = new["acceleration"])
    accel = ",".join([f"{k},{v}" for k, v in new_config.acceleration.items()])
    protocol_context.comment(f"New Accel (mm/s^2): {accel}")
    accel = ",".join([f"{k},{v}" for k, v in new_config.default_max_speed.items()])
    
    protocol_context.comment(f"New Max Speeds (mm/s): {accel}")
    protocol_context.comment("Hardware config updated to limit acceleration!")
    #  hw_api.update_config_override(new_config)
    listener = ListenerWebsocket(
        protocol_context=protocol_context,
        tips_300=tips_300,
        tips_1000=tips_1000,
        labwares=labwares,
        spincoater=spincoater,
    )
    

    # each piece of labware has to be involved in some dummy moves to be included in protocol
    # we "aspirate" from 10mm above the top of first well on each labware to get it into the protocol
    for side, p in listener.pipettes.items():
        p.move_to(listener.spincoater[listener.CHUCK].top(30), speed = listener.SLOWEST_XY_RATE)
        for name, labware in labwares.items():
            p.move_to(labware["A1"].top(30), speed = listener.SLOWEST_XY_RATE)
        for labware in tips_300:
            p.move_to(labware["A1"].top(30), speed = listener.SLOWEST_XY_RATE)
        for labware in tips_1000:
            p.move_to(labware["A1"].top(30), speed = listener.SLOWEST_XY_RATE)

    # starting with Opentrons v5.0, labware cannot be calibrated unless at least one pipette picks up a tip.
    # If we don't have a mixing netlist, then we need to pick a tip up here to calibrate the labware.
    if len(mixing_netlist) == 0:
        listener.pipettes["right"].pick_up_tip()
        listener.pipettes["right"].return_tip()
        listener.set_starting_tips()  # reset the starting tips since we just "used" one.

    ### run through the pre-experiment mixing
    # identify the generation of the final incoming transfer per each well. We will mix after this move
    final_generation = {}
    for gen_idx, generation in enumerate(mixing_netlist):
        for destination_strings in generation.values():
            for destination_str in destination_strings.keys():
                final_generation[destination_str] = gen_idx

    # run through the mixing protocol
    for gen_idx, generation in enumerate(mixing_netlist):
        for source_str, destination_strings in generation.items():
            source_labware, source_well = source_str.split("-")
            source = labwares[source_labware][source_well]

            destinations = []
            volumes = []
            is_last_transfer = []
            for destination_str, volume in destination_strings.items():
                destination_labware, destination_well = destination_str.split("-")
                if "96" in destination_labware:
                    touching = False
                else:
                    touching = True
                destinations.append(labwares[destination_labware][destination_well])
                volumes.append(volume)
                is_last_transfer.append(final_generation[destination_str] == gen_idx)

            # original_speed = listener.pipettes["right"].speed
            # listener.pipettes[
            #     "right"
            # ].speed = 100  # this is the speed we use during slow transfers
            if gen_idx == 0:
                # first generation, we dont need to worry about cross contamination

                listener.pipettes["right"].transfer(
                    volume=volumes,
                    source=source,
                    dest=destinations,
                    disposal_volume=0,
                    carryover=True,
                    mix_before=(3, 50),
                    new_tip="once",
                    blow_out=True,
                    blow_out_location="source well",
                    air_gap=20,
                    touch_tip = touching,
                )
            else:
                for dest, vol, last_transfer in zip(
                    destinations, volumes, is_last_transfer
                ):
                    if last_transfer:
                        mix_after = (
                            5,
                            50,
                        )  # mix now that all liquid has reached the well
                    else:
                        mix_after = None
                    listener.pipettes["right"].transfer(
                        volume=vol,
                        source=source,
                        dest=dest,
                        disposal_volume=0,
                        mix_before=(3, 50),
                        mix_after=mix_after,
                        blow_out=True,
                        blow_out_location="destination well",
                        touch_tip=touching,
                        air_gap=20,
                        # touch_tip = True,
                    )
            # listener.pipettes["right"].speed = original_speed

    protocol_context.comment("Ready to receive commands from Maestro")
    if protocol_context.is_simulating():  # stop here during simulation
        return

    # listen for instructions from maestro
    listener.start()
    while listener.status != STATUS_ALL_DONE:
        time.sleep(0.1)
