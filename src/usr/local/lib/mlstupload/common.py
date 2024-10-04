#! /usr/bin/python3

"Common Class and Function Definitions shared across library"

import hmac
import json
import os
import sys
import time
import urllib.parse as up
# Use pip vendored urllib3 as they would not upgrade till 2025
from pip._vendor import urllib3
VENDORED_URLLIB = True

__version_info__ = (0, 2, 1)
__version__ = ".".join((str(item) for item in __version_info__))

# Shared Variables
VERBOSE = False
DEBUG = False
CONFIG_SRC = "/etc/mlstverse/fast5upload.conf"
CONFIG = None
DATABASE_SRC = "/var/lib/mlstverse/run.db"
DATABASE = None


# Class Definitions
class WebRequest:
    """Login Session Manager and API Request Creator for Web

Usage:
    This class can be used either as a context manager, or
    manually call login() and logout() to handle the token.

    The login token is kept in item.token.

    To make a request, you may use the request() method,
    or the send_request() method.
"""

    __slots__ = ("token", "time")
    SESSION_TIMEOUT = 3600
    USER_AGENT = "mlstverse/"+__version__+" (mlstupload)"
    username = None
    password = None
    webserver = None
    fileserver = None
    pool = urllib3.PoolManager(cert_reqs="CERT_REQUIRED")
    retry = urllib3.Retry(3, allowed_methods=None)

    @classmethod
    def config_api(cls, conf):
        "Configure the API with conf object read from load_config"
        cls.username = conf["cloud"]["user"]
        cls.password = conf["cloud"]["password"]
        cls.webserver = conf["cloud"]["website_server"]
        cls.fileserver = conf["cloud"]["upload_server"]
        cls.retry = urllib3.Retry(int(conf["cloud"]["attempt"]))

    @classmethod
    def hash_password(cls, salt: str, session: str) -> str:
        "Hash the password"
        salted_pass = hmac.new(
            bytes.fromhex(salt),
            cls.password.encode("utf-8"),
            "SHA256"
        )
        sessionpass = hmac.new(
            bytes.fromhex(session.rjust(12, "0")),
            salted_pass.digest(),
            "SHA256"
        )
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
        return cls.pool.request(
            method, url,
            **{item[0]: item[1] for item in urlopen_kw.items() if item[1] is not None}
        )

    @classmethod
    def request_file(
        cls, method: str, url: str, **urlopen_kw
    ) -> urllib3.response.HTTPResponse:
        """Request wrapper for urllib3 to API, for access to FileAPI

As a higher level API, the url should be the API endpoint
However, all parameters must be manually added to the request.
"""
        return cls.send_request(
            method, os.path.join(cls.fileserver, url), **urlopen_kw
        )

    def __init__(self):
        self.token = None
        self.time = None

    def login(self):
        "Get website auth token for this instance"
        if WebRequest.username is None or WebRequest.password is None:
            raise PermissionError("Login info not set")
        resp = WebRequest.send_request(
            "POST",
            os.path.join(WebRequest.webserver, "rest/session/init"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            },
            body=up.urlencode({"name": WebRequest.username}).encode("ascii")
        )
        if resp.status != 200:
            raise PermissionError("Server maintenance")
        data = json.loads(resp.data.decode("utf-8"))
        resp = WebRequest.send_request(
            "POST",
            os.path.join(WebRequest.webserver, "rest/session/login"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body=up.urlencode({
                "id": data["id"],
                "pass": WebRequest.hash_password(
                    salt=data["hash"],
                    session=data["id"]
                )
            }).encode("ascii")
        )
        if resp.status != 202:
            raise PermissionError("Login failed")
        self.token = data["id"]
        self.time = time.time()
        print(
            "Login successful as", WebRequest.username,
            file=sys.stderr, flush=True
        )

    def logout(self):
        "Revoke the current token"
        # Logout from the web server
        if self.token is None:
            # Not successfully initialized. Do nothing
            return
        resp = WebRequest.pool.request_encode_url(
            "DELETE",
            os.path.join(WebRequest.webserver, "rest/session/login"),
            fields={"id": self.token},
            headers={"User-Agent": WebRequest.USER_AGENT}
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
            print(
                "Session Token expired. Refreshing token...",
                file=sys.stderr, flush=True
            )
            self.login()
        if headers is None:
            headers = {}
        headers["Cookie"] = "SessionID="+self.token
        urlopen_kw["body"] = body
        urlopen_kw["fields"] = fields
        urlopen_kw["headers"] = headers
        return WebRequest.send_request(
            method, os.path.join(WebRequest.webserver, url), **urlopen_kw
        )

    def __enter__(self):
        # Login to the web server
        self.login()
        return self

    def __exit__(self, *_):
        # Logout from the web server
        if None in {WebRequest.username, WebRequest.password, self.token}:
            # Not successfully initialized. Do nothing
            return
        self.logout()
