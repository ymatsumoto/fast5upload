#! /usr/bin/python3

"Upload Task Handler"

import json
import os
import queue
import sys
import time
import urllib.parse as up

from . import common

OBSERVER = None
QUEUE = queue.Queue()


def upload_file(token: str, filepath: str, bs=2097152):
    "Upload a file in small chunks to remote server"
    time.sleep(0.5)
    with open(filepath, "rb") as stdin:
        block = stdin.read(bs)
        count = 0
        while block != b"":
            # Send this block to upload server
            common.WebRequest.request_file(
                "PUT",
                "cgi-bin/upload.py",
                fields={
                    "file": ("blob", block, "application/octet-stream"),
                    "range": str(count*bs)+"-"+str(count*bs+len(block)),
                    "session": token
                }
            )
            print("=", end="", file=sys.stderr, flush=True)
            # Get next block ready
            block = stdin.read(bs)
            count += 1
    print("", file=sys.stderr, flush=True)


def create_run(conf: dict):
    "Create a new run on the server"
    mapping = common.DATABASE.get_run(conf["id"])
    with common.WebRequest() as api:
        # Connect to the Web API
        # The following segment is for enhanced token
        # user_info = json.loads(api.request(
        #    "POST",
        #    "session/info",
        #    body=up.urlencode({"id": api.token, "sign": "id,flag"})
        #    headers={
        #        "Content-Type": "application/x-www-form-urlencoded",
        #        "Accept": "application/json"
        #    }
        # ).data.decode("utf-8"))
        if mapping is None:
            # Run ID should not exist on remote server. Create it.
            print(
                "New run found. Creating run...",
                file=sys.stderr, flush=True
            )
            req = api.request(
                "POST",
                "rest/run",
                body=up.urlencode({"name": conf["name"]}),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                }
            )
            query = json.loads(req.data.decode("utf-8"))
            mapping = (query["id"], 0)
            # Record the run_id mapping somewhere
            common.DATABASE.create_run(conf["id"], query["id"])
            # Create a new run on uploadServer
            query = {
                "session": api.token,
                "id": mapping[0],
                "action": "create",
                "type": "rawdata"
            }
            req = api.request_file(
                "POST",
                "cgi-bin/createrun.py",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": common.WebRequest.webserver
                },
                body=up.urlencode(query).encode("ascii")
            )


class CreateRunTask:
    "Class to represent a create-run request"

    def __init__(self, src: str, conf: dict):
        self.src = src
        self.conf = conf

    def upload(self):
        "Create the run on the server"
        print("Initiate create_run from", self.src)
        create_run(self.conf)


class UploadTask:
    "Class to represent an upload task"

    def __init__(self, src: str, conf: dict):
        self.src = src
        self.conf = conf

    def upload(self):
        "Upload this file to the upload server"
        src_file = os.path.basename(self.src)
        src_format = os.path.splitext(src_file)[1][1:].lower()

        # Does the run exist on server?
        mapping = common.DATABASE.get_run(self.conf["id"])
        # Do we have enough data?
        if (
            mapping is not None
            and common.CONFIG["local"]["max_data"]
            and int(common.CONFIG["local"]["max_data"]) <= mapping[1]
        ):
            # We already have enough data. Skip all other uploads.
            print(
                "Max file number reached. Skipping", self.src,
                file=sys.stderr, flush=True
            )
            return

        with common.WebRequest() as api:
            # Connect to the Web API till we get upload token
            # The following segment is for enhanced token
            # user_info = json.loads(api.request(
            #    "POST",
            #    "session/info",
            #    body=up.urlencode({"id": api.token, "sign": "id,flag"})
            #    headers={
            #        "Content-Type": "application/x-www-form-urlencoded",
            #        "Accept": "application/json"
            #    }
            # ).data.decode("utf-8"))
            if mapping is None:
                # Run ID should not exist on remote server. Create it.
                print(
                    "New run found. Creating run...",
                    file=sys.stderr, flush=True
                )
                req = api.request(
                    "POST",
                    "rest/run",
                    body=up.urlencode({"name": self.conf["name"]}),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json"
                    }
                )
                query = json.loads(req.data.decode("utf-8"))
                mapping = (query["id"], 0)
                # Record the run_id mapping somewhere
                common.DATABASE.create_run(self.conf["id"], query["id"])
                # Create a new run on uploadServer
                query = {
                    "session": api.token,
                    "id": mapping[0],
                    "action": "create",
                    "type": "rawdata"
                }
                req = api.request_file(
                    "POST",
                    "cgi-bin/createrun.py",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Origin": common.WebRequest.webserver
                    },
                    body=up.urlencode(query).encode("ascii")
                )

            # Run created. Ready to upload.
            # Start of file upload, obtain an upload token
            req = api.request_file(
                "POST",
                "cgi-bin/createrun.py",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": common.WebRequest.webserver
                },
                body=up.urlencode({
                    "session": api.token,
                    "id": mapping[0],
                    "action": "upload"
                }).encode("ascii")
            )
            if req.status == 429:
                print(
                    "Upload server quota exceeded. Skipping", self.src,
                    file=sys.stderr, flush=True
                )
                return
            upload_token = req.data.decode("utf-8").strip()
        # Done with the first API call and let the file uploader to proceed
        upload_file(upload_token, self.src)
        # Upload completed. Reconnect and submit the file.
        # Close the last file
        req = common.WebRequest.request_file(
            "POST",
            "cgi-bin/upload.py",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                # "Accept": "application/json"
            },
            body=up.urlencode({
                "session": upload_token,
                "action": "close",
                "format": src_format
            }).encode("ascii")
        )
        # The following is for restified enhancement of submit response
        # target_file = json.loads(req.data.decode("utf-8"))
        target_file = {"status": req.data.decode("utf-8").strip()}
        while target_file["status"].lower() == "finalizing":
            req = common.WebRequest.request_file(
                "POST",
                "cgi-bin/upload.py",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    # "Accept": "application/json"
                },
                body=up.urlencode(
                    {"session": upload_token, "action": "finalize"}
                ).encode("ascii")
            )
            target_file = {"status": req.data.decode("utf-8").strip()}
            # target_file = json.loads(req.data.decode("utf-8"))
            # if "init" not in target_file:
            time.sleep(3)
        target_file["name"] = target_file["status"]

        # Report to webserver that the previous file has been uploaded.
        with common.WebRequest() as api:
            api.request(
                "PUT",
                os.path.join("rest/upload", mapping[0], upload_token),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=up.urlencode({
                    "barcode": "fast5",
                    "file": target_file["name"],
                    "name": src_file
                }).encode("ascii")
            )

            # Submit all uploaded file to pipeline for analysis
            api.request_file(
                "POST",
                "cgi-bin/submitfast5.py",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": common.WebRequest.webserver
                },
                body=up.urlencode({
                    "session": api.token,
                    "upload": upload_token,
                    "id": mapping[0],
                    "flowcell": self.conf["flowcell"],
                    "kit": self.conf["kit"],
                    "barcode": self.conf["barcode_kits"]
                }).encode("ascii")
            )
        # Upload successfully completed. Update the counter.
        common.DATABASE.increment_run(self.conf["id"])
        print("File", self.src, "uploaded.", file=sys.stderr, flush=True)
