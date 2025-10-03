#! /usr/bin/python3

"Python dev and debug utilities"

import code
import collections.abc
import json
import os
import readline
import rlcompleter  # pylint: disable=unused-import
import subprocess
import sys
import traceback
import uuid

from . import common
from . import config
from . import database
from . import staphminknow
from . import upload

# Note for maintenance:
#  update the cmdline.py test choice list whenever new tests were added.


class SystemTest(collections.abc.Sequence):
    "Container namespace to collect all available tests"
    api = None
    user = None

    @staticmethod
    def check_version(remote: dict, local: dict):
        "Compare local version with remote version"
        assert remote["major"] == local["major"], "Unsupported API Version"
        if remote["minor"] > local["minor"]:
            print(
                "API is using a later version than our supported version. "
                "Some functions may not work. "
                "Please consider upgrading."
            )
            return
        if remote["patch"] > local["patch"]:
            print("An update is available.")

    @staticmethod
    def library_test():
        "Checks for third-party library installations etc."
        try:
            import watchdog  # pylint: disable=import-outside-toplevel
        except ImportError:
            print(
                "Watchdog library is not found. "
                "Please reinstall this package from deb."
            )
            raise

    @staticmethod
    def minknow_test():
        "Checks for staphminknow"
        # MinKNOW Cert-Gen Bug check
        if os.path.isdir("/data/rpc-certs/minknow"):
            print(
                "ERROR: This version of MinKNOW Core comes "
                "with a certificate error."
            )
            if input(
                "Do you want to attempt auto-fix for this issue? (y/N): "
            ).lower() in ("y", "yes"):
                subprocess.run(
                    ("rm", "-frv", "/data/rpc-certs/minknow"), check=True
                )
                print("Auto-fix completed.")
        try:
            staphminknow.MinKnow.refresh()
        except Exception as error:  # pylint: disable=broad-except
            print(
                "Failed to connect to MinKNOW API. Error:",
                error,
                "Please contact support.",
                sep="\n"
            )
            raise
        print(
            "MinKNOW API test passed. "
            "The following directories would be monitored:"
        )
        print("\n".join(
            (item[0]+": \n    " + "\n    ".join(
                (subitem[0]+": "+subitem[1] for subitem in item[1].items())
            ) for item in staphminknow.MinKnow.data.items())
        ))

    @staticmethod
    def database_test():
        "Try to see if our database is working"
        random_id = uuid.uuid4()
        common.DATABASE.create_run(str(random_id), random_id.hex)
        common.DATABASE.increment_run(str(random_id))
        assert common.DATABASE.get_run(str(random_id)) == (random_id.hex, 1)
        with common.DATABASE as db_api:
            db_api.execute("DELETE FROM run WHERE local=?", (str(random_id),))
        print("Database Test passed")

    @classmethod
    def login_test(cls):
        "Login to the web API and get user info"
        cls.api = common.WebRequest()
        cls.api.login()
        cls.user = json.loads(cls.api.request(
            "POST",
            "rest/session/info",
            body=common.up.urlencode({"id": cls.api.token}).encode("ascii"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }
        ).data.decode("utf-8"))
        print("Login API Test passed")

    @classmethod
    def upload_test(cls):
        "Check upload api connectivity and version"
        if cls.api is None:
            cls.login_test()
        req = json.loads(cls.api.request_file(
            "GET",
            "cgi-bin/version.py",
            headers={
                "Accept": "application/json"
            }
        ).data.decode("utf-8"))
        cls.check_version(req, {"major": 0, "minor": 1, "patch": 0})
        print("Upload API Test passed")

    @classmethod
    def webapi_test(cls):
        "Check web api connectivity and version"
        if cls.api is None:
            cls.login_test()
        req = json.loads(cls.api.request(
            "GET",
            "rest/info",
            headers={
                "Accept": "application/json"
            }
        ).data.decode("utf-8"))
        cls.check_version(req, {"major": 0, "minor": 2, "patch": 0})
        print("Web API Test passed")

    def __init__(self, test_list: list = None):
        all_tests = {
            "library": SystemTest.library_test,
            "login": SystemTest.login_test,
            "database": SystemTest.database_test,
            "minknow": SystemTest.minknow_test,
            "upload": SystemTest.upload_test,
            "webapi": SystemTest.webapi_test
        }
        if test_list is None:
            test_list = ["all"]
        if "all" in test_list:
            test_list = list(all_tests.keys())
        self._data = []
        for item in all_tests.items():
            if item[0] in test_list:
                self._data.append(item[1])
                test_list.remove(item[0])
        if test_list:
            raise KeyError("Unsupported test " + " ".join(test_list))

    def __getitem__(self, index):
        return self._data[index]

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)


def start():
    "python entrypoint for debugging"
    config.Config.update_hook.add(common.WebRequest.config_api)
    common.CONFIG = config.Config(common.CONFIG_SRC)
    common.DEBUG = True
    common.DATABASE = database.RunDB()


def upload_test(src: str, conf: dict = None):
    "create an upload task and upload it"
    if conf is None:
        conf = staphminknow.MinKnow.get_run_info(src)
    upload_task = upload.UploadTask(src, conf)
    upload_task.upload()


def hatch(err: Exception):
    "emergency interactive shell service hatch"
    print("We hit an exception and gets into a shell for troubleshooting.")
    traceback.print_exception(err)
    readline.parse_and_bind("tab: complete")
    shell = code.InteractiveConsole(locals())
    shell.interact()


def main(test: list = None):
    "Main cmdline invocation"
    if sys.version_info.major == 2:
        print("Bundled python version is 2.")
        print(
            "Python 2 is unsupported. "
            "Are you using a supported version of MinKNOW?"
        )
        sys.exit(1)
    # start()
    # Populate the test list
    tester = SystemTest(test)
    for item in tester:
        try:
            item()
        except Exception as err:  # pylint: disable=broad-except
            print("Fatal: an error occurred in test.")
            print(err)
            print("Contact us for support if you cannot understand the error.")
            sys.exit(2)
    print(
        "All test passed. Welcome,",
        SystemTest.user["name"]  # pylint: disable=unsubscriptable-object
    )
