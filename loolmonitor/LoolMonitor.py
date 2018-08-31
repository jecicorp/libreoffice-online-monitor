#!/usr/bin/env python

import asyncio
import functools
import websockets
import socket
import logging
import os
import signal
import queue
import json

logging.config.fileConfig('logging.conf', disable_existing_loggers=False)
logger = logging.getLogger(__name__)

STATS_CMD = [
    "active_users_count",
    "active_docs_count",
    "mem_stats",
    "cpu_stats",
    "sent_activity",
    "mem_consumed",
    "total_avail_mem",
    "sent_bytes",
    "recv_bytes",
]

# Query Stats every 10s
DOCS_EVERY = 10


activ_docs = {}
adddoc = queue.Queue()
rmdoc = queue.Queue()


class LoolMonitor():
    """
    Create websocket server
    Catch SIGINT and SIGTERM to stop the server
    """

    def __init__(self, host=None, port=8765):
        logger.info("Starting Lool Monitor")
        self.__loop = None
        self.__host = host
        self.__port = port
        self.connected = set()
        self.work_handler = []

    async def consumer_handler(self, websocket, path):
        while True:
            message = await websocket.recv()
            await self.consumer(websocket, message)

    async def consumer(self, websocket, message):
        msg = message.partition(" ")
        cmd = msg[0]
        if cmd in STATS_CMD:
            k = "%s:%d/%s" % sum((websocket.remote_address, (cmd,)), ())
            self.stats[k] = msg[2]
            logger.debug(":: stats :: {}".format(msg[2]))

        elif cmd == "documents":
            data = json.loads(msg[2])
            docs = data["documents"]
            logger.debug(":: documents :: {}".format(docs))

            try:
                while True:
                    adoc_pid = adddoc.get_nowait()
                    if adoc_pid is None:
                        continue
                    for doc in docs:
                        k = self.getKey(websocket, doc["pid"])
                        if k == adoc_pid:
                            self.adddoc(doc["docKey"])
                            activ_docs[k] = doc
                            adoc_pid = None
                            break
                    adddoc.task_done()
                    if adoc_pid is not None:
                        logger.error(
                            ":: FAIL ADD DOC, {} not in documents"
                            .format(adoc_pid))
            except queue.Empty:
                pass

        elif cmd == "adddoc":
            data = msg[2].split(" ")
            pid = data[0]
            logger.debug(":: ADD doc :: {}".format(pid))
            adddoc.put(self.getKey(websocket, pid))
            await websocket.send("documents")

        elif cmd == "rmdoc":
            data = msg[2].split(" ")
            pid = data[0]
            logger.debug(":: RM doc :: {}".format(pid))
            k = self.getKey(websocket, pid)
            try:
                doc = activ_docs[k]
                logger.debug(":: Treat Rm Doc {}= {}".format(k, doc["docKey"]))
                self.rmdoc(doc["docKey"])
                del activ_docs[k]
            except KeyError:
                # Not in activ_docs
                # Todo : query documents ?
                logger.debug("RM Skip Not Found")
                pass

        elif cmd == "loolserver":
            data = json.loads(msg[2])
            logger.debug(":: Lool Server Version :: {}".format(data))

        elif cmd == "lokitversion":
            data = json.loads(msg[2])
            logger.debug(":: Lokit Version :: {}".format(data))

        elif cmd == "History":
            data = json.loads(msg[2])
            logger.debug(":: History :: {}".format(data))

        else:
            logger.debug(":: Unknow Message :: {}".format(message))

    def getKey(self, websocket, pid):
        return "%s:%d/%s" % sum((websocket.remote_address, (pid,)), ())

    async def producer_handler(self, websocket, path):
        await asyncio.wait([ws.send("version") for ws in self.connected])
        # registre pub-sub
        await asyncio.wait([
            ws.send("subscribe adddoc rmdoc resetidle modifications")
            for ws in self.connected])
        await asyncio.sleep(1)

        while True:
            await asyncio.wait([ws.send("documents") for ws in self.connected])
            await asyncio.sleep(DOCS_EVERY)

    async def handler(self, websocket, path):
        self.connected.add(websocket)
        try:
            consumer_task = asyncio.ensure_future(
                self.consumer_handler(websocket, path))
            producer_task = asyncio.ensure_future(
                self.producer_handler(websocket, path))
            done, pending = await asyncio.wait(
                [consumer_task, producer_task],
                return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()

        finally:
            self.connected.remove(websocket)

    def adddoc(self, docKey):
        for h in self.work_handler:
            h.adddoc(docKey)

    def rmdoc(self, docKey):
        for h in self.work_handler:
            h.rmdoc(docKey)

    def ask_exit(self, signame):
        logger.info("got signal %s: exit" % signame)
        for h in self.work_handler:
            h.stop()
        self.__loop.stop()

    def __init_event_loop(self):
        self.__loop = asyncio.get_event_loop()
        for signame in ('SIGINT', 'SIGTERM'):
            self.__loop.add_signal_handler(
                getattr(signal, signame),
                functools.partial(self.ask_exit, signame))

    def start(self):
        logger.info("Start Monitor")
        start_server = websockets.serve(self.handler,
                                        self.__host,
                                        self.__port,
                                        family=socket.AF_INET, ssl=None)

        logger.info("listing on 'ws://{}:{}'".format(self.__host, self.__port))
        logger.info("Event loop running forever, press Ctrl+C to interrupt.")
        logger.info("pid %s: send SIGINT or SIGTERM to exit." % os.getpid())

        try:
            self.__init_event_loop()
            self.__loop.run_until_complete(start_server)
            self.__loop.run_forever()
        finally:
            self.__loop.close()
