#!/opt/ont/minknow/ont-python/bin/python
#/usr/bin/env python

import hmac
import json
import os
import queue
import re
import signal
import sqlite3
import sys
import threading
import time
import urllib.parse as up

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import minknow_api

try:
    import urllib3
    VENDORED_URLLIB = False
except ModuleNotFoundError:
    from pip._vendor import urllib3
    VENDORED_URLLIB = True

if not urllib3.__version__.startswith("1.26."):
    raise ImportError("Unsupported urllib3 version")

__doc__ = "A tool to automatically upload MinKNOW data for analysis"

__version__ = (0,2,0)

UPLOAD_QUEUE = queue.Queue()

## Class Definitions
class WebRequest:
    """Login Session Manager and API Request Creator for Web

Usage:
    This class can be used either as a context manager, or
    manually call login() and logout() to handle the token.

    The login token is kept in item.token.

    To make a request, you may use the request() method,
    or the send_request() method.
"""

    __slots__ = ( "token", "time" )
    SESSION_TIMEOUT = 3600
    USER_AGENT = "mlstverse/0.2 (mlstupload)"
    username  = None
    password  = None
    webserver = None
    fileserver= None
    pool      = urllib3.PoolManager( cert_reqs = "CERT_REQUIRED" )
    retry     = urllib3.Retry( 3, allowed_methods=None )

    @classmethod
    def config_api(cls, conf):
        "Configure the API with conf object read from load_config"
        cls.username  = conf["cloud"]["user"]
        cls.password  = conf["cloud"]["password"]
        cls.webserver = conf["cloud"]["website_server"]
        cls.fileserver= conf["cloud"]["upload_server"]
        cls.retry     = urllib3.Retry( conf["cloud"]["attempt"] )

    @classmethod
    def hash_password(cls, salt: str, session: str) -> str:
        "Hash the password"
        salted_pass = hmac.new(bytes.fromhex(salt),cls.password.encode("utf-8"),"SHA256")
        sessionpass = hmac.new(bytes.fromhex(session.rjust(12,"0")),salted_pass.digest(),"SHA256")
        return sessionpass.hexdigest()

    @classmethod
    def send_request(
        cls,
        method: str, url: str, body=None, fields=None, headers=None,
        **urlopen_kw
    ) -> urllib3.response.HTTPResponse:
        "Request wrapper for urllib3 to API for class"
        if headers is None:
            headers = {}
        if "User-Agent" not in headers:
            headers["User-Agent"] = cls.USER_AGENT
        if "retries" not in urlopen_kw:
            urlopen_kw["retries"] = cls.retry
        urlopen_kw["body"] = body
        urlopen_kw["fields"] = fields
        urlopen_kw["headers"] = headers
        return cls.pool.request(method, url, **urlopen_kw)

    def __init__(self):
        self.token = None
        self.time = None

    def login(self):
        "Get website auth token for this instance"
        if WebRequest.username is None or WebRequest.password is None:
            raise PermissionError("Login info not set")
        resp = WebRequest.send_request(
            "POST",
            WebRequest.webserver + "rest/session/init",
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            },
            body = up.urlencode({"name": WebRequest.username}).encode("ascii")
        )
        if resp.status != 200:
            raise PermissionError("Server maintenance")
        data = json.loads(resp.data.decode("utf-8"))
        resp = WebRequest.send_request(
            "POST",
            WebRequest.webserver + "rest/session/login",
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body = up.urlencode({
                "id": data["id"],
                "pass": WebRequest.hash_password(salt = data["hash"], session = data["id"])
            }).encode("ascii")
        )
        if resp.status != 202:
            raise PermissionError("Login failed")
        self.token = data["id"]
        self.time = time.time()
        print("Login successful as", WebRequest.username, file=sys.stderr, flush=True)

    def logout(self):
        "Revoke the current token"
        ## Logout from the web server
        if self.token is None:
            # Not successfully initialized. Do nothing
            return
        resp = WebRequest.pool.request_encode_url(
            "DELETE",
            WebRequest.webserver + "rest/session/login",
            fields = {"id": self.token},
            headers = {"User-Agent": WebRequest.USER_AGENT}
        )
        if resp.status == 202:
            print("Logout sucessful.")
            return
        print("Logout failed, error code:", resp.status)

    def request(
        self,
        method: str, url: str, body=None, fields=None, headers=None,
        **urlopen_kw
    ) -> urllib3.response.HTTPResponse:
        """Request wrapper for urllib3 to API, for access to WebAPI

As a higher level API, the url should be the API endpoint, and the
headers may omit the Cookie part as the token would be automatically
added to the request.
"""
        if self.time + WebRequest.SESSION_TIMEOUT < time.time():
            print("Session Token expired. Refreshing token...", file=sys.stderr, flush=True)
            self.login()
        if headers is None:
            headers = {}
        headers["Cookie"] = "SessionID="+self.token
        urlopen_kw["body"] = body
        urlopen_kw["fields"] = fields
        urlopen_kw["headers"] = headers
        return WebRequest.send_request(method, WebRequest.webserver + url, **urlopen_kw)

    def __enter__(self):
        ## Login to the web server
        self.login()
        return self

    def __exit__(self, *_):
        ## Logout from the web server
        if WebRequest.username is None or WebRequest.password is None or self.token is None:
            # Not successfully initialized. Do nothing
            return
        self.logout()

class FileModifyHandler(FileSystemEventHandler):
    "Watchdog Override to trigger upload_fast5 when a fast5/pod5 is found"
    def on_moved(self, event):
        "Handle File Move Event"
        ext = os.path.splitext(event.dest_path)[1]
        if ext in (".fast5", ".pod5"):
            print("Processing", event.dest_path, file=sys.stderr, flush=True)
            try:
                ## Attempt to queue a file for uploading
                ## Get the run info at the same time as we found the file
                run_info = get_run_info()
                if run_info is not None:
                    UPLOAD_QUEUE.put((event.dest_path, run_info))
            except Exception as err:
                print(
                    "Failed to upload file",
                    event.dest_path, ":", err,
                    file=sys.stderr,
                    flush=True
                )
        else:
            print("Skipping", event.dest_path, file=sys.stderr, flush=True)


## Function Definitions
def load_config(callback: tuple = tuple()) -> dict:
    "Load configurations from file"
    default = {
        "local": {
            "runid_db": "/var/lib/mlstverse/run.db",
            "data": "/var/lib/minknow/data",
            "port": 8000,
            "max_data": None
        },
        "cloud": {
            "user": None,
            "password": None,
            "attempt": 3,
            "website_server": "https://mlstverse.org/",
            "upload_server": "https://www.gen-info.osaka-u.ac.jp/realtime-mlstverse/"
        }
    }
    try:
        with open('/etc/mlstverse/fast5upload.conf', "r", encoding="utf-8") as stdin:
            conf = json.load(stdin)
        for param,value in default.items():
            if param not in conf:
                conf[param] = value
            else:
                for key, val in value.items():
                    if key not in conf[param]:
                        conf[param][key] = val
    except FileNotFoundError:
        conf = default
    ## Apply the configurations
    for item in callback:
        item(conf)
    return conf

def get_run_info() -> dict:
    "Get run info from MinKNOW API"
    def get_barcode(kit: str):
        "Guess the barcoding kit from kit"
        return "SQK-NBD112-96" if kit[:7] == "SQK-LSK" else kit

    conf = load_config()
    ## DEBUG MODE: Use a predetermined run config
    if "debug" in conf:
        return conf["debug"]["run"]
    ## DEBUG MODE end

    run = {
        'user': None,
        'id': None,
        'name': "", # so that later re.search would not break
        'flowcell': 'FLO-MIN106',
        'kit': 'SQK-RBK004',
        'barcode_kits': 'SQK-RBK004'
    }
    try:
    # from minknow_api import Connection
        con = minknow_api.Connection(port=conf["local"]["port"])
        info = con.protocol.get_run_info()
    except Exception as error:
        print("Error occurred when connecting to MinKNOW", error, file=sys.stderr, flush=True)
        return None

    try:
        run["user"] = conf["cloud"]["user"]
        run[  "id"] = info.run_id
        run["name"] = info.user_info.protocol_group_id.value
        run["flowcell"] = info.protocol_id.split(':')[1]
        run[ "kit"] = info.protocol_id.split(':')[2]
        run["barcode_kits"] = get_barcode(run["kit"])
    except Exception as error:
        print("Error occurred when parsing run info:",error, file=sys.stderr, flush=True)
        return None
    return run

def upload_file(token: str, filepath: str, bs=2097152):
    "Upload a file in small chunks to remote server"
    time.sleep(0.5)
    with open(filepath,"rb") as stdin:
        block = stdin.read(bs)
        count = 0
        while block != b"":
            ## Send this block to upload server
            WebRequest.send_request(
                "PUT",
                WebRequest.fileserver + "cgi-bin/upload.py",
                fields = {
                    "file": ("blob", block, "application/octet-stream"),
                    "range": str(count*bs)+"-"+str(count*bs+len(block)),
                    "session": token
                }
            )
            print("=",end="", file=sys.stderr, flush=True)
            ## Get next block ready
            block = stdin.read(bs)
            count += 1
    print("", file=sys.stderr, flush=True)

def upload_fast5(database: dict, path: str, run_info: dict = None, rescan: bool = False):
    "Upload the specified file to the server for analysis"
    ## Expect path to be a single file pending upload
    ## If rescan is True, it would upload any file that is not uploaded

    ## Gather information
    src_file = os.path.basename(path)
    src_format = os.path.splitext(src_file)[1][1:].lower()
    conf = load_config()
    if conf["cloud"]["user"] is None:
        return
    run = run_info
    if run is None:
        ## If the run info is not provided, we obtain one ourself.
        run = get_run_info()
        if run is None:
            return
    ## If the trigger is not for our run, we skip the upload
    if not re.search(run["name"], path):
        return

    with WebRequest() as api:
        ## Connect to the Web API till we get upload token
        ## Does the run exist on server?
        db = sqlite3.connect(database["path"])
        cur = db.cursor()
        mapping = cur.execute("SELECT remote, count FROM run WHERE local=?",(run["id"],)).fetchone()

        if mapping is None:
            ## Run ID should not exist on remote server. Create it.
            ## Connect to Web API
            ## Create a new run on webServer
            print("New run found. Creating run...", file=sys.stderr, flush=True)
            req = api.request(
                "POST",
                "rest/run",
                body=up.urlencode({"name":run["name"]}),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                }
            )
            query = json.loads(req.body.decode("utf-8"))
            mapping = (query["id"], 0)
            ## Record the run_id mapping somewhere
            cur.execute("INSERT INTO run VALUES (?,?,?)",(run["id"],query["id"],0))
            cur.close()
            ## Create a new run on uploadServer
            query = {
                "session":api.token,
                "id":query[0],
                "action":"create",
                "type":"rawdata",
                "flowcell":run["flowcell"],
                "kit":run["kit"],
                "barcode":run["barcode_kits"]
            }
            req = WebRequest.send_request(
                "POST",
                WebRequest.fileserver + "cgi-bin/createrun.py",
                headers = {"Content-Type": "application/x-www-form-urlencoded"},
                body = up.urlencode(query).encode("ascii")
            )
        if conf["local"]["max_data"] == mapping[1]:
            ## We already have enough data. Skip all other uploads.
            print("Max file number reached. Skipping", path, file=sys.stderr, flush=True)
            db.close()
            return
        db.commit()
        db.close() # Don't need the mapping any more.
        ## Run created. Ready to upload.
        if rescan:
            ## If we need to rescan the not-uploaded list, do this
            blacklist = set()

            completed = json.loads(api.request(
                "GET",
                "cgi-bin/uploadinfo.py",
                fields = {
                    "action": "check",
                    "id": mapping[0]
                }
            ).data.decode("utf-8"))
            if completed["type"] == "fast5":
                blacklist = set(completed["file"])
            elif completed["type"] == "mixed":
                blacklist = set(completed["file"]["fast5"])
            pending_list = set((
                item.name for item in os.scandir(os.path.dirname(path))
                if os.path.splitext(item.name)[1] not in ("fast5","pod5")
            ))
            ## Pick one from the not uploaded file list and upload it.
            path = os.path.join(
                os.path.dirname(path),
                next(iter(pending_list.difference(blacklist)))
            )

        ## Start of file upload, obtain an upload token
        req = WebRequest.send_request(
            "POST",
            WebRequest.fileserver + "cgi-bin/createrun.py",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=up.urlencode({
                "session": api.token,
                "id": mapping[0],
                "action": "upload"
            }).encode("ascii")
        )
        upload_token = req.body.decode("utf-8").strip()
        ## Done with the first API call and let the file uploader to proceed

    upload_file(upload_token, path)
    ## Upload completed. Reconnect and submit the file.
    ## Close the last file
    req = WebRequest.send_request(
        "POST",
        WebRequest.fileserver + "cgi-bin/upload.py",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        },
        body = up.urlencode({
            "session": upload_token,
            "action": "close",
            "format": src_format
        }).encode("ascii")
    )
    target_file = json.loads(req.body.decode("utf-8"))
    while target_file["status"] == "finalizing":
        req = WebRequest.send_request(
            "POST",
            WebRequest.fileserver + "cgi-bin/upload.py",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            },
            body=up.urlencode({"session": upload_token, "action": "finalize"}).encode("ascii")
        )
        target_file = json.loads(req.body.decode("utf-8"))
        if "init" not in target_file:
            time.sleep(3)

    ## Report to webserver that the previous file has been uploaded.
    with WebRequest() as api:
        api.request(
            "POST",
            "cgi-bin/uploadinfo.py",
            headers = {"Content-Type": "application/x-www-form-urlencoded"},
            body = up.urlencode({
                "action": "upload",
                "upload": upload_token,
                "id": mapping[0],
                "barcode": "fast5",
                "file": target_file["name"],
                "name": src_file
            }).encode("ascii")
        )

        ## Submit all uploaded file to pipeline for analysis
        WebRequest.send_request(
            "POST",
            WebRequest.fileserver + "cgi-bin/submitfast5.py",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=up.urlencode({
                "session": api.token,
                "upload": upload_token,
                "id": mapping[0],
                "flowcell": run["flowcell"],
                "kit": run["kit"],
                "barcode": run["barcode_kits"]
            }).encode("ascii")
        )
    ## Upload successfully completed. Update the counter.
    db = sqlite3.connect(database["path"])
    cur = db.cursor()
    cur.execute("UPDATE run SET uploaded = uploaded+1 WHERE local=?", (run["id"],))
    db.commit()
    db.close()
    print("File", path, "uploaded.", file=sys.stderr, flush=True)

def stop_upload(sig: int, _):
    "Put the termination signal to the upload queue"
    print("Termination requested by signal", sig)
    UPLOAD_QUEUE.put(None)

## Function for Threads
def upload_thread():
    "The thread that single-threadedly handle all uploads"
    DATABASE = {
        "path": None,
        "schema": "CREATE TABLE run (local text primary key, remote text unique, uploaded int)"
    }

    def load_database(conf: dict):
        "Update schema as needed and load it to DATABASE"
        ## We are expecting no connections established to DB
        path = conf["local"]["runid_db"]
        if DATABASE["path"] == path:
            ## No need to reload. We still use the same DB
            return
        result = sqlite3.connect(path)
        cur = result.cursor()
        check = cur.execute(
            "SELECT sql FROM sqlite_schema WHERE type=? AND name=?",
            ("table", "run")
        ).fetchone()
        if check and check[0] == DATABASE["schema"]:
            ## Check passed
            result.close()
            return
        if check and check[0] != DATABASE["schema"]:
            cur.execute("DROP TABLE run")
        cur.execute(DATABASE["schema"])
        result.commit()
        result.close()

    DATABASE["reload"] = load_database

    ## Initialize finished
    print("Upload thread started.", file=sys.stderr, flush=True)
    req = UPLOAD_QUEUE.get()
    while req is not None:
        ## Do processing, expecting req as a tuple of filename, runinfo
        upload_fast5(DATABASE, req[0], req[1])
        req = UPLOAD_QUEUE.get()
    print("Upload thread completed.", file=sys.stderr, flush=True)

def main():
    "Main cmdline invocation, main thread"
    ## Init configuration: WebAPI and Database
    conf = load_config(callback = (WebRequest.config_api,))
    if conf["cloud"]["user"] is None:
        print("Fatal Error: Web API User not set. Please set it in the configuration file.")
        sys.exit(1)

    ## Watchdog setup
    observer = Observer()
    event_handler = FileModifyHandler()
    observer.schedule(event_handler, conf["local"]["data"], recursive=True)
    observer.start()
    print("Start monitoring "+conf["local"]["data"], file=sys.stderr, flush=True)
    ## Upload thread setup
    upload_worker = threading.Thread(target=upload_thread)
    upload_worker.start()
    ## Signal handling for end of life
    signal.signal(signal.SIGINT, stop_upload)
    signal.signal(signal.SIGTERM, stop_upload)
    ## Wait for everything to stop
    upload_worker.join()
    observer.stop()
    observer.join()
    print("Process terminated successfully.", file=sys.stderr, flush=True)

if __name__ == "__main__":
    main()
