#! /usr/bin/python3

"Watchdog daemon that monitors the creation of new data files"

import os
import signal
import sys

# Import third-party
import watchdog.observers
import watchdog.events

from . import common
from . import staphminknow
from . import upload


class FileModifyHandler(watchdog.events.FileSystemEventHandler):
    "Watchdog Override to trigger upload_fast5 when a fast5/pod5 is found"
    def on_moved(self, event):
        "Handle File Move Event"
        ext = os.path.splitext(event.dest_path)[1]
        if ext in (".fast5", ".pod5"):
            try:
                # Attempt to queue a file for uploading
                # Get the run info at the same time as we found the file
                run_info = staphminknow.MinKnow.get_run_info(event.dest_path)
                if run_info is not None:
                    # We have a valid data file to upload. Queue it.
                    print("Queued", event.dest_path, file=sys.stderr, flush=True)
                    upload.QUEUE.put(
                        upload.UploadTask(event.dest_path, run_info)
                    )
            except Exception as err:  # pylint: disable=broad-except
                print(
                    "Failed to upload file",
                    event.dest_path, ":", err,
                    file=sys.stderr, flush=True
                )
        else:
            if common.VERBOSE:
                print("Skipping", event.dest_path, file=sys.stderr, flush=True)


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
