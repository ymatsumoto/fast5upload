#! /usr/bin/python3

"Configuration handler for user config"

import configparser
import json
import os

from . import common

TEMPLATE_CONF = {
    "local": {
        "runid_db": "/var/lib/mlstverse/run.db",
        "data": "/var/lib/minknow/data",
        "max_data": ""
    },
    "cloud": {
        "attempt": "3",
        "website_server": "https://mlstverse.org",
        "upload_server":
            "https://www.gen-info.osaka-u.ac.jp/realtime-mlstverse"
    }
}


class Config(configparser.ConfigParser):
    "Configuration Wrapper"
    update_hook = set()

    def __init__(self, src: str):
        if not os.path.isfile(src):
            raise FileNotFoundError(src)
        reload_json = None
        with open(src, "r", encoding="utf-8") as stdin:
            if stdin.read(1) == "{":
                # JSON Config detected. Reencode.
                stdin.seek(0)
                reload_json = json.load(stdin)
        self.update = 0
        self.src = src
        super().__init__()
        if reload_json is not None:
            self.read_dict(reload_json)
            try:
                with open(src, "w", encoding="utf-8") as stdout:
                    self.write(stdout)
            except Exception:  # pylint: disable=broad-except
                print("Failed to automatically update config format.")
        self.reload()

    def reload(self):
        "Load config"
        last_update = os.stat(self.src).st_mtime_ns
        if last_update > self.update:
            # New update is available
            self.read(self.src, encoding="utf-8")
            assert "cloud" in self and "local" in self, "Incomplete config"
            self.update = last_update
            assert self["cloud"]["user"], "Username not in config"
            assert self["cloud"]["password"], "Password not in config"
            # Check and fill void
            for item in TEMPLATE_CONF.items():
                for entry in item[1].items():
                    if self[item[0]].get(entry[0]) is None:
                        self[item[0]][entry[0]] = entry[1]
            for item in Config.update_hook:
                item(self)
            if common.VERBOSE:
                print("Config file refreshed.")
