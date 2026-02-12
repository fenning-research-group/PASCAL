import asyncio
import json
import random
import socket
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import websockets

from frgpascal.experimentaldesign.protocolwriter import generate_ot2_protocol
from frgpascal.hardware.liquidhandler import OT2Server

TIME_SYNC_ERROR_TOLERANCE_S = 0.05
SCHEDULE_ERROR_TOLERANCE_S = 0.10
TARGET_TEMPLATES = [
    "1000left300right",
    "1000left300right-lightsON",
    "samepipettebothsides",
]


def _get_free_local_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class DummyLabware:
    name: str
    version: str
    deck_slot: str
    contents: list = field(default_factory=list)


@dataclass
class DummyTiprack:
    version: str
    deck_slot: str
    unavailable_tips: list = field(default_factory=list)


class MockOT2Endpoint:
    def __init__(
        self,
        host="127.0.0.1",
        port=8764,
        clock_offset=0.6,
        clock_jitter=0.0,
        network_jitter=0.005,
        rng_seed=7,
        support_time_sync=True,
    ):
        self.host = host
        self.port = port
        self.clock_offset = clock_offset
        self.clock_jitter = clock_jitter
        self.network_jitter = network_jitter
        self.support_time_sync = support_time_sync
        self.local_nist_offset = 0.0
        self.received_time_offsets = []
        self.received_tasks = []
        self.all_completed_tasks = {}
        self._rng = random.Random(rng_seed)
        self._loop = None
        self._thread = None
        self._server = None
        self._send_lock = None
        self._ready = threading.Event()

    def nist_time(self):
        jitter = self._rng.uniform(-self.clock_jitter, self.clock_jitter)
        return time.time() + self.clock_offset + jitter + self.local_nist_offset

    async def _send_json(self, websocket, payload):
        await asyncio.sleep(self._rng.uniform(0.0, self.network_jitter))
        async with self._send_lock:
            await websocket.send(json.dumps(payload))

    async def _complete_task(self, websocket, task):
        taskid = task["taskid"]
        execute_at = float(task["nist_time"])
        sleep_for = max(0.0, execute_at - self.nist_time())
        await asyncio.sleep(sleep_for)
        self.all_completed_tasks[taskid] = self.nist_time()
        await self._send_json(websocket, {"completed": dict(self.all_completed_tasks)})

    async def _handler(self, websocket, path=None):
        try:
            async for raw in websocket:
                maestro = json.loads(raw)

                if "time_sync" in maestro and self.support_time_sync:
                    req = maestro["time_sync"]
                    await self._send_json(
                        websocket,
                        {
                            "time_sync": {
                                "id": req.get("id"),
                                "host_time": req.get("host_time"),
                                "ot2_time": self.nist_time(),
                            }
                        },
                    )

                if "set_time_offset" in maestro and self.support_time_sync:
                    req = maestro["set_time_offset"]
                    self.local_nist_offset = float(req["offset"])
                    self.received_time_offsets.append(self.local_nist_offset)
                    await self._send_json(
                        websocket,
                        {"set_time_offset": {"offset": self.local_nist_offset}},
                    )

                if "task" in maestro:
                    task = maestro["task"]
                    taskid = task["taskid"]
                    self.received_tasks.append(task)
                    await self._send_json(websocket, {"acknowledged": taskid})
                    asyncio.create_task(self._complete_task(websocket, task))

                if "status" in maestro:
                    await self._send_json(
                        websocket, {"completed": dict(self.all_completed_tasks)}
                    )

                if "complete" in maestro:
                    break
        except websockets.exceptions.ConnectionClosed:
            pass

    async def _start_server(self):
        self._send_lock = asyncio.Lock()
        self._server = await websockets.serve(self._handler, self.host, self.port)
        self._ready.set()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._start_server())
        self._loop.run_forever()
        self._server.close()
        self._loop.run_until_complete(self._server.wait_closed())
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        self._loop.close()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Mock OT-2 endpoint failed to start.")

    def stop(self):
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


def _wait_for_tasks(server, taskids, timeout_s=20):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if all(taskid in server.completed_tasks for taskid in taskids):
            return
        time.sleep(0.02)
    missing = [taskid for taskid in taskids if taskid not in server.completed_tasks]
    raise TimeoutError(f"Timed out waiting for completed tasks: {missing}")


def _check_generator_output():
    labware = [
        DummyLabware(
            name="testplate",
            version="corning_96_wellplate_360ul_flat",
            deck_slot="1",
            contents=[{"A1": 1}],
        )
    ]
    tipracks_300 = [
        DummyTiprack(
            version="opentrons_96_tiprack_300ul",
            deck_slot="2",
            unavailable_tips=[],
        )
    ]
    tipracks_1000 = [
        DummyTiprack(
            version="opentrons_96_tiprack_1000ul",
            deck_slot="3",
            unavailable_tips=[],
        )
    ]
    expected_payload_tokens = ['"task"', '"taskid"', '"nist_time"', '"args"', '"kwargs"']

    with tempfile.TemporaryDirectory() as tmpdir:
        for template in TARGET_TEMPLATES:
            title = f"offline_sim_{template.replace('-', '_')}"
            generate_ot2_protocol(
                title=title,
                mixing_netlist=[],
                labware=labware,
                tipracks_300=tipracks_300,
                tipracks_1000=tipracks_1000,
                directory=tmpdir,
                template=template,
            )
            protocol_path = Path(tmpdir) / f"OT2PASCALProtocol_{title}.py"
            content = protocol_path.read_text(encoding="utf-8")

            if "time_sync" not in content or "set_time_offset" not in content:
                raise AssertionError(
                    f"Generated protocol for template '{template}' is missing offline sync path."
                )
            for token in expected_payload_tokens:
                if token not in content:
                    raise AssertionError(
                        f"Generated protocol for template '{template}' missing token {token}."
                    )


def run_offline_integration_simulation():
    checks = []
    port = _get_free_local_port()
    mock = MockOT2Endpoint(
        port=port,
        clock_offset=0.6,
        clock_jitter=0.002,
        network_jitter=0.005,
        rng_seed=23,
    )
    server = OT2Server()
    server.ip = "127.0.0.1"
    server.port = port

    mock.start()
    try:
        server._start_directly()

        if not mock.received_time_offsets:
            raise AssertionError("Clock sync did not send set_time_offset to mock OT-2.")
        applied_offset = mock.received_time_offsets[-1]
        expected_offset = (server.nist_time - time.time()) - mock.clock_offset
        offset_error = abs(applied_offset - expected_offset)
        if offset_error > TIME_SYNC_ERROR_TOLERANCE_S:
            raise AssertionError(
                f"Clock sync error too large ({offset_error:.3f}s > {TIME_SYNC_ERROR_TOLERANCE_S:.3f}s)."
            )
        checks.append("Clock sync correctness")

        base_time = server.nist_time + 0.6
        deltas = [0.4, 0.8, 1.2]
        task_ids = []
        for idx, delta in enumerate(deltas):
            task_ids.append(
                server.add_to_queue(
                    task="mock_task",
                    taskid=f"scheduled-{idx}",
                    nist_time=base_time + delta,
                )
            )
        _wait_for_tasks(server, task_ids, timeout_s=15)
        completion_times = [server.completed_tasks[taskid] for taskid in task_ids]
        if completion_times != sorted(completion_times):
            raise AssertionError("Scheduled tasks completed out of order.")
        for taskid, delta in zip(task_ids, deltas):
            actual_delta = server.completed_tasks[taskid] - base_time
            if abs(actual_delta - delta) > SCHEDULE_ERROR_TOLERANCE_S:
                raise AssertionError(
                    f"Task {taskid} timing error {abs(actual_delta - delta):.3f}s exceeds tolerance."
                )
        checks.append("Scheduled task execution invariance")

        t0 = server.nist_time
        probe_taskid = server.add_to_queue(
            task="mock_task", taskid="timebase-probe", nist_time=t0 + 0.5
        )
        _wait_for_tasks(server, [probe_taskid], timeout_s=10)
        drop_time = server.completed_tasks[probe_taskid] - t0
        if drop_time < 0.35 or drop_time > 1.2:
            raise AssertionError(
                f"Completion timestamp is not sane in host timebase: drop_time={drop_time:.3f}s."
            )
        checks.append("Completion timestamp host timebase compatibility")

        replay_t0 = server.nist_time
        replay_taskids = []
        for idx, delta in enumerate([0.45, 0.65, 0.95]):
            replay_taskids.append(
                server.add_to_queue(
                    task="mock_task",
                    taskid=f"replay-{idx}",
                    nist_time=replay_t0 + delta,
                )
            )
        _wait_for_tasks(server, replay_taskids, timeout_s=10)
        replay_drop_times = [
            server.completed_tasks[taskid] - replay_t0 for taskid in replay_taskids
        ]
        if any(drop_time < 0 for drop_time in replay_drop_times):
            raise AssertionError("Worker-style drop_time replay produced negative times.")
        checks.append("Worker-contract replay")

        _check_generator_output()
        checks.append("Protocol generator compatibility")
    finally:
        if hasattr(server, "_worker"):
            try:
                server.stop()
            except Exception:
                pass
        elif hasattr(server, "loop"):
            try:
                server.loop.call_soon_threadsafe(server.loop.stop)
            except Exception:
                pass
        mock.stop()

    legacy_port = _get_free_local_port()
    legacy_mock = MockOT2Endpoint(port=legacy_port, support_time_sync=False)
    legacy_server = OT2Server()
    legacy_server.ip = "127.0.0.1"
    legacy_server.port = legacy_port
    legacy_mock.start()
    try:
        legacy_server._start_directly()
        if legacy_mock.received_time_offsets:
            raise AssertionError(
                "Legacy listener unexpectedly received set_time_offset messages."
            )
        legacy_taskid = legacy_server.add_to_queue(
            task="mock_task",
            taskid="legacy-compat",
            nist_time=legacy_server.nist_time + 0.5,
        )
        _wait_for_tasks(legacy_server, [legacy_taskid], timeout_s=10)
        checks.append("Backward compatibility with legacy listener protocol")
    finally:
        if hasattr(legacy_server, "_worker"):
            try:
                legacy_server.stop()
            except Exception:
                pass
        elif hasattr(legacy_server, "loop"):
            try:
                legacy_server.loop.call_soon_threadsafe(legacy_server.loop.stop)
            except Exception:
                pass
        legacy_mock.stop()

    strict_port = _get_free_local_port()
    strict_mock = MockOT2Endpoint(port=strict_port, support_time_sync=False)
    strict_server = OT2Server()
    strict_server.ip = "127.0.0.1"
    strict_server.port = strict_port
    strict_server.require_offline_time_sync = True
    strict_mock.start()
    try:
        try:
            strict_server._start_directly()
        except RuntimeError as exc:
            if "missing offline time_sync support" not in str(exc):
                raise AssertionError(
                    "Strict mode fail-fast error did not include the expected guidance."
                ) from exc
        else:
            raise AssertionError(
                "Expected strict-mode fail-fast when listener lacks offline time_sync support."
            )
        checks.append("Strict-mode fail-fast guard for outdated listener protocol")
    finally:
        if hasattr(strict_server, "_worker"):
            try:
                strict_server.stop()
            except Exception:
                pass
        elif hasattr(strict_server, "loop"):
            try:
                strict_server.loop.call_soon_threadsafe(strict_server.loop.stop)
            except Exception:
                pass
        strict_mock.stop()

    return checks


if __name__ == "__main__":
    completed_checks = run_offline_integration_simulation()
    for check in completed_checks:
        print(f"[PASS] {check}")
    print("[PASS] Offline OT-2 integration simulation complete.")
