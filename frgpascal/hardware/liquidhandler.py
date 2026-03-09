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
    """
    Estimate the duration required for liquid aspiration for a given drop.

    Parameters
    ----------
    drop : dict
        Dictionary of drop parameters containing keys like 'volume', 'pre_mix', 
        'touch_tip', 'slow_retract', 'air_gap', and 'slow_travel'.

    Returns
    -------
    aspirate_duration : float
        Estimated duration to aspirate the liquid, in seconds.
    staging_duration : float
        Estimated duration to travel and stage the pipette, in seconds.
    dispense_duration : float
        Estimated duration to dispense the liquid, in seconds.
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
    """
    High-level control interface for the Opentrons OT-2 liquid handler. 

    This class acts as a job packager and coordinator. It does not execute 
    commands natively but packages them into formatted JSON dictionaries and 
    pushes them to the `OT2Server` queue, which communicates with the physical 
    robot over a network WebSocket.

    Parameters
    ----------
    server : OT2Server, optional
        A pre-initialized server object to handle network communications. 
        If None, a new `OT2Server` is instantiated.

    Attributes
    ----------
    server : OT2Server
        The server handling the WebSocket connection to the robot.
    POLLINGRATE : float
        The polling interval in seconds.
    CONSTANTS : dict
        Hardware timing constants loaded from the configuration file.
    """
    def __init__(self, server = None):
        if server is None:
            self.server = OT2Server()
        else:
            self.server = server
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
        """
        Queue a task to dispense perovskite solution onto the spin coater chuck.

        Parameters
        ----------
        taskid : str, optional
            A unique identifier for the task. If None, one is generated automatically.
        nist_time : float, optional
            The NIST-synchronized timestamp for execution.
        **kwargs
            Additional arguments packaged into the command (e.g., rate, height).

        Returns
        -------
        str
            The unique identifier assigned to this task.
        """
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
        """
        Queue a task to dispense antisolvent onto the spin coater

        Parameters
        ----------
        taskid : str, optional
            A unique identifier for the task.
        nist_time : float, optional
            The NIST-synchronized timestamp for execution.
        **kwargs
            Additional arguments packaged into the command.

        Returns
        -------
        str
            The unique identifier assigned to this task.
        """
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
        """
        Queue a task to aspirate liquid from a specified well in preparation for spin coating.

        Parameters
        ----------
        tray : str
            The name or identifier of the source tray.
        well : str
            The specific well to aspirate from (e.g., 'A1').
        volume : float
            The volume of liquid to aspirate in microliters.
        pipette : str, optional
            The pipette designation to use, by default "perovskite".
        slow_retract : bool, optional
            Whether to retract the pipette slowly to prevent droplets, by default True.
        air_gap : bool, optional
            Whether to pull an air gap after aspiration, by default True.
        touch_tip : bool, optional
            Whether to touch the tip to the side of the well, by default True.
        pre_mix : tuple of int, optional
            ` (repetitions, volume)` for mixing before aspiration, by default (0, 0).
        reuse_tip : bool, optional
            Whether to keep the tip attached for future use, by default False.
        taskid : str, optional
            A unique identifier for the task.
        nist_time : float, optional
            The NIST-synchronized timestamp for execution.
        **kwargs
            Additional arguments packaged into the command.

        Returns
        -------
        str
            The unique identifier assigned to this task.
        """
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
        """
        Queue a task to move the perovskite pipette into position over the spin coater.

        Parameters
        ----------
        taskid : str, optional
            A unique identifier for the task.
        nist_time : float, optional
            The NIST-synchronized timestamp for execution.
        slow_travel : bool, optional
            Whether to move the gantry slowly, by default False.
        **kwargs
            Additional arguments packaged into the command.

        Returns
        -------
        str
            The unique identifier assigned to this task.
        """
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
        """
        Queue a task to move the antisolvent pipette into position over the spin coater.

        Parameters
        ----------
        taskid : str, optional
            A unique identifier for the task.
        nist_time : float, optional
            The NIST-synchronized timestamp for execution.
        slow_travel : bool, optional
            Whether to move the gantry slowly, by default False.
        **kwargs
            Additional arguments packaged into the command.

        Returns
        -------
        str
            The unique identifier assigned to this task.
        """
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
        """
        Queue a task to move the pipettes away from the spin coater chuck

        Parameters
        ----------
        taskid : str, optional
            A unique identifier for the task.
        nist_time : float, optional
            The NIST-synchronized timestamp for execution.
        **kwargs
            Additional arguments packaged into the command.

        Returns
        -------
        str
            The unique identifier assigned to this task.
        """
        taskid = self.server.add_to_queue(
            task="clear_chuck",
            taskid=taskid,
            nist_time=nist_time,
            **kwargs,
        )
        return taskid

    def cleanup(self, taskid=None, nist_time=None, **kwargs):
        """
        Queue a task to perform general liquid handler cleanup (e.g., dropping tips).

        Parameters
        ----------
        taskid : str, optional
            A unique identifier for the task.
        nist_time : float, optional
            The NIST-synchronized timestamp for execution.
        **kwargs
            Additional arguments packaged into the command.

        Returns
        -------
        str
            The unique identifier assigned to this task.
        """
        taskid = self.server.add_to_queue(
            task="cleanup",
            taskid=taskid,
            nist_time=nist_time,
            **kwargs,
        )
        return taskid

    def mix(self, taskid=None, nist_time=None, mixing_netlist={}):
        """
        Queue a task to mix solutions according to a provided netlist

        Parameters
        ----------
        taskid : str, optional
            A unique identifier for the task.
        nist_time : float, optional
            The NIST-synchronized timestamp for execution.
        mixing_netlist : dict, optional
            Instructions for mixing operations, by default {}.

        Returns
        -------
        str
            The unique identifier assigned to this task.
        """
        taskid = self.server.add_to_queue(
            task="mix",
            taskid=taskid,
            nist_time=nist_time,
            mixing_netlist=mixing_netlist,
        )
        return taskid

    def mark_completed(self):
        """
        Signal the server to conclude its operations and cleanly shut down
        """
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
        """
        Block execution until the server confirms the specific task has been completed.

        Parameters
        ----------
        taskid : str
            The unique identifier of the task to wait for.
        """
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
    """
    WebSocket server for managing asynchronous communication with the Opentrons OT-2 robot.

    This class handles the underlying network connection, queues tasks in JSON 
    format, and maintains exact NIST clock synchronization to ensure drop timing 
    precisely aligns with the spin coater

    Attributes
    ----------
    connected : bool
        Whether the WebSocket connection is currently active.
    ip : str
        The IP address of the OT-2 robot.
    port : int
        The network port for the WebSocket connection.
    pending_tasks : list
        List of task IDs that have been sent but not yet marked complete.
    completed_tasks : dict
        Dictionary of completed task IDs mapped to their completion timestamps.
    POLLINGRATE : float
        Interval in seconds between checking the status of the OT-2.
    loop : asyncio.AbstractEventLoop
        The event loop managing asynchronous background tasks.
    """
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
        """
        Pings an NTP server to determine the local clock offset relative to NIST time
        """
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
        """
        Get the current precise time adjusted by the NIST offset.

        Returns
        -------
        float
            The synchronized Unix timestamp.
        """
        return time.time() + self.__local_nist_offset

    ### Server Methods
    async def __connect_to_websocket(self):
        """
        Asynchronously establish the WebSocket connection to the physical OT-2.
        """
        try:
            print(f"\t\ttrying to delete self.websocket attribute")
            del self.websocket
            print(f'\t\tsuccessfully deleted self.websocket attribute')
        except:
            print(f"\t\tfailed to delete self.websocket attribute.\n\t\t\to.k. if first sample, weird otherwise")
            pass  # if this is the first time, we wont have a websocket. thats fine
        print(f"\t\tattempting to connect to websocket with uri address: {self.uri}")
        self.websocket = await websockets.connect(
            self.uri, ping_interval=20, ping_timeout=300
        )
        print(f"\t\tseems to have connected?")

    def start(self, ip=None, port=None):
        """
        Initialize the background thread and connect to the robot, prompting for user confirmation.

        Parameters
        ----------
        ip : str, optional
            Override the target IP address.
        port : int, optional
            Override the target port.
        """
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
        """
        Silently initialize the background thread and connect to the robot without user prompting
        """
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
        """
        Shut down the background worker and close the WebSocket connection.
        """
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
        """
        Update the internal statuses of pending and completed tasks

        Parameters
        ----------
        tasklist : dict
            Dictionary containing task IDs mapped to their completion timestamps.
        """
        for taskid, nisttime in tasklist.items():
            # print(f"{taskid} completed at {nisttime}")
            if taskid in self.pending_tasks:
                self.pending_tasks.remove(taskid)
        self.completed_tasks.update(tasklist)

    async def worker(self):
        """
        Continuous background coroutine that listens for WebSocket messages from the OT-2.
        """
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
        """
        Pushes a task JSON to the WebSocket.

        Parameters
        ----------
        task : dict
            The formatted task dictionary.
        """
        # print(task)
        await self.websocket.send(json.dumps(task))

    def _add_task(self, task):
        """
        Thread-safe wrapper to schedule a task to be sent over the WebSocket.

        Parameters
        ----------
        task : dict
            The formatted task dictionary.
        """
        asyncio.run_coroutine_threadsafe(self.__add_task(task), loop=self.loop)
        # # asyncio.create_task(self.__add_task(task))
        # asyncio.run_coroutine_threadsafe(self.__add_task(task), self.loop)

    def add_to_queue(self, task, taskid=None, nist_time=None, *args, **kwargs):
        """
        Construct a final task dictionary and add it to the execution queue.

        Parameters
        ----------
        task : str
            The primary command label (e.g., "dispense_onto_chuck").
        taskid : str, optional
            A unique identifier. If None, one is generated.
        nist_time : float, optional
            The target NIST time for execution.
        *args
            Positional arguments for the task.
        **kwargs
            Keyword arguments for the task.

        Returns
        -------
        str
            The assigned task ID.
        """
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
        """
        Send a status update request to the OT2
        """
        maestro = {"status": 0}
        self._add_task(maestro)

    def mark_completed(self):
        """
        Send a completion signal to the OT-2 to wrap up operations.
        """
        maestro = {"complete": 0}
        self._add_task(maestro)
