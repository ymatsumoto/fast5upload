#! /usr/bin/python3

"Wrapper script to interact with minknow_api"

import hashlib
import importlib
import os
import sys
import time

from . import common

# MinKNOW API Library Handling
try:
    MINKNOW_API = importlib.import_module("minknow_api")
    importlib.import_module(".manager", "minknow_api")
except ImportError:
    MINKNOW_API = importlib.import_module(".minknow_api_debug", __package__)
    # this module comes with manager. no need to import that manually


class MinKnow:
    "MinKnow wrapper to get run information from API"
    DEFAULT_BARCODE_KIT = "SQK-NBD112-96"
    data = {}
    updated = 0

    @staticmethod
    def _sequencer_filter(name: str) -> bool:
        if (
            "sequencer" in common.CONFIG["local"]
            and common.CONFIG["local"]["sequencer"]
        ):
            return name in common.CONFIG["local"]["sequencer"].split(",")
        return True

    @classmethod
    def _get_barcode(cls, kit: str) -> str:
        "Guess the barcoding kit from kit"
        if kit.startswith("SQK-LSK"):
            if "default_kit" in common.CONFIG["local"]:
                return common.CONFIG["local"]["default_kit"]
            return cls.DEFAULT_BARCODE_KIT
        return kit

    @classmethod
    def _get_basecall_param(cls, info) -> dict:
        "Get basecall parameter from MinKNOW API Connection"
        run = {
            'user': None,
            'id': None,
            'name': "",  # so that later re.search would not break
            'flowcell': 'FLO-MIN106',
            'kit': 'SQK-RBK004',
            'barcode_kits': 'SQK-RBK004'
        }
        try:
            run["user"] = common.CONFIG["cloud"]["user"]
            run["id"] = info.run_id
            run["name"] = info.user_info.protocol_group_id.value
            run["flowcell"] = info.protocol_id.split(':')[1]
            run["kit"] = info.protocol_id.split(':')[2]
            run["barcode_kits"] = cls._get_barcode(run["kit"])
        except Exception as error:  # pylint: disable=broad-except
            print(
                "Error occurred when parsing run info:", error,
                file=sys.stderr, flush=True
            )
            return None
        return run

    @classmethod
    def _get_default_param(cls, filepath: str) -> dict:
        "Get basecall parameter from estimation"
        def uuid_formatter(orig: str) -> str:
            "format a md5sum hexdump string into uuid format"
            return "-".join((orig[:8], orig[8:12], orig[12:16], orig[16:20], orig[20:]))
        run_name = os.path.basename(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(filepath))))
        )
        run = {
            "user": common.CONFIG["cloud"]["user"],
            "id": uuid_formatter(hashlib.md5(run_name.encode("ascii")).hexdigest()),
            "name": run_name,
            "flowcell": "FLO-MIN114",
            "kit": "SQK-RBK114-96",
            "barcode_kits": "SQK-RBK114-96"
        }
        return run

    @classmethod
    def refresh(cls):
        "Get MinKNOW sequencing positions and their config"
        man = MINKNOW_API.manager.Manager()
        seq_pos = [
            item.connect().protocol.get_run_info()
            for item in man.flow_cell_positions()
        ]
        result = {}
        for info in seq_pos:
            if (
                cls._sequencer_filter(info.device.device_id)
                and info.protocol_id.startswith("sequencing/")
            ):
                # Potentially a run that matches the current file
                runpath = os.path.normpath(info.output_path)
                runinfo = cls._get_basecall_param(info)
                if runinfo is not None:
                    result[runpath] = runinfo
        cls.data = result
        cls.updated = time.time()

    @classmethod
    def get_run_info(cls, path: str) -> dict:
        "Get run info for the path of the data file"
        data_path = os.path.dirname(os.path.dirname(path))
        if data_path in cls.data:
            return cls.data[data_path]
        try:
            cls.refresh()
        except Exception as error:  # pylint: disable=broad-except
            print("Updating sequencer position info failed.", error, file=sys.stderr, flush=True)
            return cls._get_default_param(path)
        if data_path in cls.data:
            return cls.data[data_path]
        return None
