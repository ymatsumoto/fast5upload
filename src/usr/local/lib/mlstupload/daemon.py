#! /usr/bin/python3

"Watchdog daemon that monitors the creation of new data files"

import os
import signal
import socket
import sys

# Import third-party
import watchdog.observers
import watchdog.events

from . import common
from . import staphminknow
from . import upload


class FileModifyHandler(watchdog.events.FileSystemEventHandler):
    "Watchdog Override to trigger upload_fast5 when a fast5/pod5 is found"
    dedup = set()

    @staticmethod
    def _handle_run_directory(path: str):
        "Handle new directory for run creation"
        if os.path.dirname(
            os.path.dirname(os.path.dirname(path))
        ) != common.CONFIG["local"]["data"]:
            # Subdir need to be ignored
            return
        run_info = staphminknow.MinKnow.get_run_info(path, True)
        if run_info is not None:
            # Create the new run on browser.
            # Duplication is handled automatically as
            # in upload we do a DB lookup for the run id
            print("New run directory detected.")
            upload.QUEUE.put(
                upload.CreateRunTask(path, run_info)
            )
            # upload.create_run(run_info)

    @staticmethod
    def _handle_signal_file(path: str):
        "Handle signal file for uploading etc"
        ext = os.path.splitext(path)[1]
        if ext in (".fast5", ".pod5"):
            if (
                path in FileModifyHandler.dedup and
                not path.startswith("reup")
            ):
                return  # duplicate
            elif os.path.basename(path) == "DAEMON_WATCH_TEST.pod5":
                print(
                    "fast5upload_debug file detected.",
                    file=sys.stderr, flush=True
                )
                try:
                    with open(path, "r", encoding="utf-8") as stdin:
                        callback = stdin.read().strip()
                    os.remove(path)
                    os.rmdir(os.path.dirname(path))
                    with socket.socket(
                        socket.AF_UNIX, socket.SOCK_STREAM
                    ) as sock:
                        sock.connect("\0"+callback)
                        sock.sendall(b"OK")
                except Exception as err:
                    print(
                        "An exception occurred when processing debug",
                        err, file=sys.stderr, flush=True
                    )
                return  # debug
            else:
                FileModifyHandler.dedup.add(path)
            try:
                # Attempt to queue a file for uploading
                # Get the run info at the same time as we found the file
                run_info = staphminknow.MinKnow.get_run_info(path)
                if run_info is not None:
                    # We have a valid data file to upload. Queue it.
                    print(
                        "C: Queued", path,
                        file=sys.stderr, flush=True
                    )
                    upload.QUEUE.put(
                        upload.UploadTask(path, run_info)
                    )
            except Exception as err:  # pylint: disable=broad-except
                print(
                    "Failed to upload file",
                    path, ":", err,
                    file=sys.stderr, flush=True
                )
        else:
            if common.VERBOSE:
                print("Skipping", path, file=sys.stderr, flush=True)

    def on_created(self, event: watchdog.events.FileSystemEvent):
        "Handle FileCreate event from move directory"
        if isinstance(event, watchdog.events.DirCreatedEvent):
            if common.VERBOSE:
                print("+", event.src_path, file=sys.stderr, flush=True)
            FileModifyHandler._handle_run_directory(event.src_path)
        if isinstance(event, watchdog.events.FileCreatedEvent):
            if common.VERBOSE:
                print("+", event.src_path, file=sys.stderr, flush=True)
            FileModifyHandler._handle_signal_file(event.src_path)

    def on_moved(self, event: watchdog.events.FileSystemEvent):
        "Handle FileMove event from rename"
        if isinstance(event, watchdog.events.DirCreatedEvent):
            if common.VERBOSE:
                print(
                    event.src_path, "->", event.dest_path,
                    file=sys.stderr, flush=True
                )
            FileModifyHandler._handle_run_directory(event.dest_path)
        if isinstance(event, watchdog.events.FileMovedEvent):
            if common.VERBOSE:
                print(
                    event.src_path, "->", event.dest_path,
                    file=sys.stderr, flush=True
                )
            FileModifyHandler._handle_signal_file(event.dest_path)


def start_monitor():
    "setup watchdog to monitor the path"
    observer = watchdog.observers.Observer()
    event_handler = FileModifyHandler()
    observer.schedule(
        event_handler, common.CONFIG["local"]["data"],
        recursive=True
    )
    observer.start()
    print(
        "Start monitoring "+common.CONFIG["local"]["data"],
        file=sys.stderr, flush=True
    )
    upload.OBSERVER = observer


def stop_monitor(sig: int, _):
    "Put the termination signal to the upload queue"
    print("Termination requested by signal", sig, file=sys.stderr, flush=True)
    upload.QUEUE.put(None)
    if upload.OBSERVER is not None:
        upload.OBSERVER.stop()
        upload.OBSERVER.join()
        upload.OBSERVER = None
        print("Watchdog terminated successfully.", file=sys.stderr, flush=True)


def main():
    "main invocation to start the upload daemon"
    start_monitor()
    # Signal handling for end of life
    signal.signal(signal.SIGINT, stop_monitor)
    signal.signal(signal.SIGTERM, stop_monitor)
    # Upload loop
    while True:
        task = upload.QUEUE.get()
        if task is None:
            break
        task.upload()
    print("Daemon terminated successfully.", file=sys.stderr, flush=True)
