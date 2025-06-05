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

tc = constants["timings"]


def expected_timings(drop):
    """Estimate the duration (seconds) liquid aspiration will require for a given drop

    Args:
        drop (dict): dictionary of drop parameters

    Returns:
        float: duration, in seconds
    """
    ac = tc["aspirate"]  # aspiration constants
    aspirate_duration = ac["preparetip"] + drop["volume"] / 100 + tc["travel"]
    aspirate_duration += drop["pre_mix"][0] * (
        ac["premix"]["a"] * drop["pre_mix"][1] + ac["premix"]["b"]
    )  # overhead time for aspirate+dispense cycles to mix solution prior to final aspiration
    if drop["touch_tip"]:
        aspirate_duration += ac["touchtip"]
    if drop["slow_retract"]:
        aspirate_duration += ac["slowretract"]
    if drop["air_gap"]:
        aspirate_duration += ac["airgap"]

    if drop["slow_travel"]:
        staging_duration = tc["travel_slow"]
        dispense_duration = tc["dispensedelay_slow"]
    else:
        staging_duration = tc["travel"]
        dispense_duration = tc["dispensedelay"]

    return aspirate_duration, staging_duration, dispense_duration


class OT2:
    def __init__(self):
        self.server = OT2Server()
        # self.server.start()
        self.POLLINGRATE = constants["pollingrate"]
        # self.DISPENSE_DELAY = constants[
        #     "dispense_delay"
        # ]  # time (seconds) between initiating a dispense and the completion of the dispense
        # self.ASPIRATION_DELAY = constants[
        #     "aspiration_delay"
        # ]  # time (seconds) to perform an aspiration and stage the pipette
        # self.STAGING_DELAY = constants[
        #     "staging_delay"
        # ]  # time (seconds) to move pipette into position for drop staging
        self.CONSTANTS = constants["timings"]

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
        pre_mix=(0, 0),
        reuse_tip=False,
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
            reuse_tip=reuse_tip,
            pre_mix=pre_mix,
            **kwargs,
        )
        return taskid

    def stage_perovskite(
        self, taskid=None, nist_time=None, slow_travel=False, **kwargs
    ):
        taskid = self.server.add_to_queue(
            task="stage_for_dispense",
            taskid=taskid,
            nist_time=nist_time,
            pipette="perovskite",
            slow_travel=slow_travel,
            **kwargs,
        )
        return taskid

    def stage_antisolvent(
        self, taskid=None, nist_time=None, slow_travel=False, **kwargs
    ):
        taskid = self.server.add_to_queue(
            task="stage_for_dispense",
            taskid=taskid,
            nist_time=nist_time,
            pipette="antisolvent",
            slow_travel=slow_travel,
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

    def mix(self, taskid=None, nist_time=None, mixing_netlist={}):
        taskid = self.server.add_to_queue(
            task="mix",
            taskid=taskid,
            nist_time=nist_time,
            mixing_netlist=mixing_netlist,
        )
        return taskid

    def mark_completed(self):
        print("Running self.server._start_directly() now")
        self.server._start_directly()
        print("\tSuccess!")
        print("Running self.server._mark_completed() now")
        self.server.mark_completed()
        print("\tSuccess!")
        print("Running self.server._stop() now")
        self.server.stop()
        print("\tSuccess!")

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

    @property
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
        print("\tstarting daemon thread")
        self.thread = threading.Thread(target=run_loop, args=(self.loop,))
        self.thread.daemon = True
        self.thread.start()
        print("\tstarting to connect to websocket")
        asyncio.run_coroutine_threadsafe(self.__connect_to_websocket(), self.loop)
        # self.loop.call_soon_threadsafe(self.__connect_to_websocket)
        print("\twaiting to connect")
        while not hasattr(self, "websocket"):
            time.sleep(0.1)  # wait to connect

        if hasattr(self, 'websocket'):
            print("\t\tWebsocket connection seems to have worked.")
        else:
            print("\t\tWebsocket connection silently failed!")
        # print("\twebsocket connected!")
        self.connected = True
        print("\tstarting OT2Server coroutine thread")
        self._worker = asyncio.run_coroutine_threadsafe(self.worker(), self.loop)

    def stop(self):
        # self.mark_completed()
        self._timeout_duration = 10
        self.connected = False
        time.sleep(1)
        print("\tStopping OT2Server worker")
        self._worker.cancel()
        self.loop.call_soon_threadsafe(self.loop.stop)
        # asyncio.gather(self._worker, self._checker)
        # self.loop.close()
        print("\twaiting for OT2Server thread to stop.")
        # self.thread.join()
        print(f"\t{self.thread}")
        print(f"Thread we are waiting to stop: \n\t{self.thread.name}")
        # print(f"Thread we are waiting to stop: \n\t{self.thread.name}\n\t\t{self.thread._target}")
        if self.thread.isDaemon:
            try: 
                self.thread.join(timeout = self._timeout_duration)
                if self.thread.is_alive():
                    print(f"\t{self.thread} did not end before the timeout of {self._timeout_duration} s, so thread is still alive")
                else:
                    print(f"\t{self.thread} ended, so it is dead.")
            except Exception as e:
                print(f"\tWe tried to stop this Daemon thread, but this exception arose:\n\t\t{e}")
        else:
            try:
                self.thread.join()
            except Exception as e:
                print(f"Something went wrong?\n{e}")
        print("\tthread stopped, now deleting the OT2 connection.")
        if hasattr(self, "websocket"):
            del self.websocket
        else:
            print(f"\t{self} does not have a websocket?? \n\t\tSkipping this `del self.websocket` command for now.")

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
            nist_time = self.nist_time

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
