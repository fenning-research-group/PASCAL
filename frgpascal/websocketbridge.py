import asyncio
import websockets
from threading import Thread
from abc import ABC, abstractmethod
from functools import partial

PORT = 8765


def future_callback(source, future):
    try:
        future.result()
    except Exception as e:
        print(f"Exception in {source}: {future.exception()}")
        # if future.exception(): #your long thing had an exception
        #     self.logger.error(f'Exception in {self}: {future.exception()}')


class WebsocketBase(ABC):
    def __init__(self):
        self.running = False
        # self.loop.run_until_complete(client_main())

    async def consumer_handler(self, websocket):
        while self.running:
            async for message in websocket:
                # print(f"{self} received: {message}")
                self._process_message(message)

    async def producer_handler(self, websocket):
        while self.running:
            try:
                protocol = self.queue.get_nowait()
                await websocket.send(protocol)
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)

    @abstractmethod
    async def _process_message(self, message: str):
        """processes incoming messages from the websocket"""
        pass

    @abstractmethod
    async def _main(self):
        """initiates the websocket. changes depending on server vs client child class"""
        pass

    def _start_in_new_thread(self, loop):
        asyncio.set_event_loop(loop)
        self.queue = asyncio.Queue()
        loop.run_forever()

    def run(self):
        if self.running:
            raise Exception("Already running!")
        self.running = True
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self._start_in_new_thread, args=(self.loop,))
        self.thread.start()
        asyncio.run_coroutine_threadsafe(self._main(), self.loop)

    def stop(self):
        if not self.running:
            raise Exception("Not running!")
        self.running = False
        self.loop.stop()
        self.thread.join()

        pending = asyncio.all_tasks(loop=self.loop)
        for task in pending:
            task.cancel()
            # Now we should await task to execute it's cancellation.
            # Cancelled task raises asyncio.CancelledError that we can suppress:
            try:
                self.loop.run_until_complete(task)
            except:  # asyncio.exceptions.CancelledError:
                pass
        # self.loop.run_until_complete(asyncio.wait(pending))
        # for task in asyncio.all_tasks(loop=self.loop):
        #     task.cancel()

    def send(self, msg: str):
        """Sends a string message over the websocket

        Args:
            msg (str): any message, often this is a PASCAL protocol in json format

        Raises:
            Exception: Can only add to queue when websocket is running
        """
        if not self.running:
            raise Exception("Server is not running, cannot add message to queue!")
        self.loop.call_soon_threadsafe(self.queue.put_nowait, msg)


class Client(WebsocketBase):
    def __init__(self):
        super().__init__()
        self.run()
        # self.loop.run_until_complete(client_main())

    async def _main(self):
        async with websockets.connect(f"ws://localhost:{PORT}") as websocket:
            consumer_task = asyncio.create_task(self.consumer_handler(websocket))
            producer_task = asyncio.create_task(self.producer_handler(websocket))
            for future in [consumer_task, producer_task]:
                future.add_done_callback(partial(future_callback, self))
            done, pending = await asyncio.wait(
                [consumer_task, producer_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            # print(f"{self} done, {pending} pending")

            # for task in asyncio.all_tasks(loop=self.loop):
            #     task.cancel()


### Maestro side (server)
class Server(WebsocketBase):
    def __init__(self):
        super().__init__()
        self.run()
        # self.loop.run_until_complete(client_main())

    async def server_handler(self, websocket, path):
        consumer_task = asyncio.create_task(self.consumer_handler(websocket))
        producer_task = asyncio.create_task(self.producer_handler(websocket))
        for future in [consumer_task, producer_task]:
            future.add_done_callback(partial(future_callback, self))
        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # print(f"{self} done, {pending} pending")
        # for task in pending:
        #     task.cancel()
        # consumer_task = self.loop.call_soon_threadsafe(self.consumer_handler, websocket)
        # producer_task = self.loop.call_soon_threadsafe(self.producer_handler, websocket)
        # done, pending = await asyncio.wait(
        #     [consumer_task, producer_task],
        #     return_when=self.loop.FIRST_COMPLETED,
        # )
        # for task in pending:
        #     task.cancel()

    async def _main(self):
        async with websockets.serve(self.server_handler, "localhost", PORT):
            while self.running:
                await asyncio.sleep(0.1)
