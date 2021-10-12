import numpy as np
import asyncio
import time
import ntplib
import json
import os
import yaml
import websockets
import threading
import uuid
import logging

MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["liquidhandler"]


class OT2:
    def __init__(self):
        self.server = OT2Server()
        # self.server.start()
        self.POLLINGRATE = constants["pollingrate"]
        self.DISPENSE_DELAY = constants[
            "dispense_delay"
        ]  # time (seconds) between initiating a dispense and the completion of the dispense
        self.ASPIRATION_DELAY = constants[
            "aspiration_delay"
        ]  # time (seconds) to perform an aspiration and stage the pipette
        self.STAGING_DELAY = constants[
            "staging_delay"
        ]  # time (seconds) to move pipette into position for drop staging
        self.CONSTANTS = constants

    def drop_perovskite(self, taskid=None, nist_time=None, **kwargs):
        taskid = self.server.add_to_queue(
            task="dispense_onto_chuck",
            taskid=taskid,
            nist_time=nist_time,
            pipette="perovskite",
            # height=height,
            # rate=rate,
            **kwargs,
        )
        return taskid

    def drop_antisolvent(self, taskid=None, nist_time=None, **kwargs):
        taskid = self.server.add_to_queue(
            task="dispense_onto_chuck",
            taskid=taskid,
            nist_time=nist_time,
            pipette="antisolvent",
            **kwargs,
        )
        return taskid

    def aspirate_for_spincoating(
        self,
        tray,
        well,
        volume,
        pipette="perovskite",
        slow_retract=True,
        air_gap=True,
        touch_tip=True,
        taskid=None,
        nist_time=None,
        **kwargs,
    ):
        taskid = self.server.add_to_queue(
            task="aspirate_for_spincoating",
            taskid=taskid,
            nist_time=nist_time,
            tray=tray,
            well=well,
            volume=volume,
            pipette=pipette,
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
            **kwargs,
        )
        return taskid

    def aspirate_both_for_spincoating(
        self,
        psk_tray,
        psk_well,
        psk_volume,
        antisolvent_tray,
        antisolvent_well,
        antisolvent_volume,
        slow_retract=True,
        air_gap=True,
        touch_tip=True,
        taskid=None,
        nist_time=None,
        **kwargs,
    ):
        taskid = self.server.add_to_queue(
            task="aspirate_both_for_spincoating",
            taskid=taskid,
            nist_time=nist_time,
            psk_tray=psk_tray,
            psk_well=psk_well,
            psk_volume=psk_volume,
            as_tray=antisolvent_tray,
            as_well=antisolvent_well,
            as_volume=antisolvent_volume,
            slow_retract=slow_retract,
            air_gap=air_gap,
            touch_tip=touch_tip,
            **kwargs,
        )
        return taskid

    def stage_perovskite(self, taskid=None, nist_time=None, **kwargs):
        taskid = self.server.add_to_queue(
            task="stage_for_dispense",
            taskid=taskid,
            nist_time=nist_time,
            pipette="perovskite",
            **kwargs,
        )
        return taskid

    def stage_antisolvent(self, taskid=None, nist_time=None, **kwargs):
        taskid = self.server.add_to_queue(
            task="stage_for_dispense",
            taskid=taskid,
            nist_time=nist_time,
            pipette="antisolvent",
            **kwargs,
        )
        return taskid

    def clear_chuck(self, taskid=None, nist_time=None, **kwargs):
        taskid = self.server.add_to_queue(
            task="clear_chuck",
            taskid=taskid,
            nist_time=nist_time,
            **kwargs,
        )
        return taskid

    def cleanup(self, taskid=None, nist_time=None, **kwargs):
        taskid = self.server.add_to_queue(
            task="cleanup",
            taskid=taskid,
            nist_time=nist_time,
            **kwargs,
        )
        return taskid

    def mark_completed(self):
        self.server._start_directly()
        self.server.mark_completed()
        self.server.stop()

    def wait_for_task_complete(self, taskid):
        while taskid not in self.server.completed_tasks:
            time.sleep(self.POLLINGRATE)
        # while taskid not in self.server.completed_tasks:
        #     time.sleep(self.server.POLLINGRATE)
        # while self.server.OT2_status == 0:  # wait for task to be acknowledged by ot2
        #     time.sleep(self.INTERVAL)
        # while self.server.OT2_status != 0:  # wait for task to be marked complete by ot2
        #     time.sleep(self.INTERVAL)

    def __del__(self):
        self.server.stop()


class OT2Server:
    def __init__(self):
        self.__calibrate_time_to_nist()
        self.connected = False
        self.ip = constants["server"]["ip"]
        self.port = constants["server"]["port"]
        self.pending_tasks = []
        self.completed_tasks = {}
        self.POLLINGRATE = 1  # seconds between status checks to OT2
        self.loop = asyncio.new_event_loop()

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
    async def __connect_to_websocket(self):
        try:
            del self.websocket
        except:
            pass  # if this is the first time, we wont have a websocket. thats fine
        self.websocket = await websockets.connect(
            self.uri, ping_interval=20, ping_timeout=300
        )

    def start(self, ip=None, port=None):
        if ip is not None:
            self.ip = ip
        if port is not None:
            self.port = port
        self.uri = f"ws://{self.ip}:{self.port}"

        flag = input("confirm that the Listener protocol is running on OT2 (y/n):")
        if str.lower(flag) == "y":

            def run_loop(loop):
                asyncio.set_event_loop(loop)
                loop.run_forever()

            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(target=run_loop, args=(self.loop,))
            self.thread.daemon = True
            self.thread.start()
            asyncio.run_coroutine_threadsafe(self.__connect_to_websocket(), self.loop)
            while not hasattr(self, "websocket"):
                time.sleep(0.2)  # wait to connect
            self.connected = True
            self._worker = asyncio.run_coroutine_threadsafe(self.worker(), self.loop)
            # self._checker = asyncio.run_coroutine_threadsafe(self.checker(), self.loop)
            # self.loop.call_soon_threadsafe(self.worker)
            # self.loop.call_soon_threadsafe(self.checker)
            # self.loop.run_until_complete(self.__connect_to_websocket())

            # self.thread.daemon = True
            # self.thread.start()

            # self.loop.run_forever()

            # self._worker = self.loop.create_task(self.worker(), name="maestro_worker")
            # self._checker = self.loop.create_task(
            #     self.checker(), name="maestro_checker"
            # )
            # def f():
            #     self.loop = asyncio.new_event_loop()
            #     self.loop.run_until_complete(self._start_workers())
            #     # self.loop.run_forever()

            # self.thread = threading.Thread(target=f, args=())
            # self.thread.run()
            # self.loop.run_until_complete(self.__connect_to_websocket())
            # self.loop.run_forever()
            # self._worker = asyncio.create_task(self.worker(), name="maestro_worker")
            # self._checker = asyncio.create_task(self.checker(), name="maestro_checker")
            # self.thread = threading.Thread(target=self._start_workers, args=())
            # self.thread.start()
            # self._start_workers()
        else:
            print(
                "User indicated that Listener protocol is not running - did not attempt to connect to OT2 websocket."
            )

    def _start_directly(self):
        self.uri = f"ws://{self.ip}:{self.port}"

        def run_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self.thread = threading.Thread(target=run_loop, args=(self.loop,))
        self.thread.daemon = True
        self.thread.start()
        asyncio.run_coroutine_threadsafe(self.__connect_to_websocket(), self.loop)
        # self.loop.call_soon_threadsafe(self.__connect_to_websocket)
        while not hasattr(self, "websocket"):
            time.sleep(0.1)  # wait to connect
        self.connected = True
        self._worker = asyncio.run_coroutine_threadsafe(self.worker(), self.loop)

    def stop(self):
        # self.mark_completed()
        self.connected = False
        time.sleep(1)
        self._worker.cancel()
        self.loop.call_soon_threadsafe(self.loop.stop)
        # asyncio.gather(self._worker, self._checker)
        # self.loop.close()
        self.thread.join()
        del self.websocket

    def _update_completed_tasklist(self, tasklist):
        for taskid, nisttime in tasklist.items():
            # print(f"{taskid} completed at {nisttime}")
            if taskid in self.pending_tasks:
                self.pending_tasks.remove(taskid)
        self.completed_tasks.update(tasklist)

    async def worker(self):
        while self.connected:
            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=0.5)
                ot2 = json.loads(response)
            except asyncio.TimeoutError:
                ot2 = {}
            except websockets.exceptions.ConnectionClosed:  # reconnect
                del self.websocket
                asyncio.run_coroutine_threadsafe(
                    self.__connect_to_websocket(), self.loop
                )
                # self.loop.call_soon_threadsafe(self.__connect_to_websocket)
                while not hasattr(self, "websocket"):
                    time.sleep(0.1)  # wait to connect
            # print(f"maestro recieved {ot2}")
            if "acknowledged" in ot2:
                # print(f'{ot2["acknowledged"]} acknowledged by OT2')
                self.pending_tasks.append(ot2["acknowledged"])
            if "completed" in ot2:
                self._update_completed_tasklist(ot2["completed"])

    async def __add_task(self, task):
        # print(task)
        await self.websocket.send(json.dumps(task))

    def _add_task(self, task):
        asyncio.run_coroutine_threadsafe(self.__add_task(task), loop=self.loop)
        # # asyncio.create_task(self.__add_task(task))
        # asyncio.run_coroutine_threadsafe(self.__add_task(task), self.loop)

    def add_to_queue(self, task, taskid=None, nist_time=None, *args, **kwargs):
        if taskid is None:
            taskid = str(uuid.uuid4())

        if nist_time is None:
            nist_time = self.nist_time()

        task = {
            "task": {
                "task": task,
                "taskid": taskid,
                "nist_time": nist_time,
                "args": args,
                "kwargs": kwargs,
            }
        }
        self._add_task(task)
        return taskid

    def status_update(self):
        maestro = {"status": 0}
        self._add_task(maestro)

    def mark_completed(self):
        maestro = {"complete": 0}
        self._add_task(maestro)
