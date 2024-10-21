#! /usr/bin/python3

"Command Line Invocation Module - Run as daemon"

import argparse

from . import common
from . import config
from . import database


def main():
    "Main cmdline invocation point"
    # Parse the argument and start the daemon
    parser = argparse.ArgumentParser(prog=__package__)
    parser.add_argument("-c", "--config", help="config file")
    parser.add_argument(
        "-d", "--debug",
        action="store_true", help="debug mode"
    )
    parser.add_argument(
        "-t", "--test",
        action="append",
        choices=(
            "login", "upload", "webapi",
            "database", "minknow", "library",
            "all"
        ),
        help="run tests only and quit"
    )
    parser.add_argument(
        "-v", "--version",
        action="version", version="%(prog)s "+common.__version__
    )
    args = parser.parse_args()
    # Populate the fields
    config.Config.update_hook.add(common.WebRequest.config_api)
    common.VERBOSE = args.debug
    common.CONFIG_SRC = args.config or common.CONFIG_SRC
    common.CONFIG = config.Config(common.CONFIG_SRC)
    common.DATABASE = database.RunDB()
    # Run the daemon
    if args.test:
        from . import debug  # pylint: disable=import-outside-toplevel
        debug.main(args.test)
        return
    if args.debug:
        from . import debug  # pylint: disable=import-outside-toplevel
        from . import daemon  # pylint: disable=import-outside-toplevel
        try:
            daemon.main()
        except Exception as err:  # pylint: disable=broad-except
            debug.hatch(err)
        return
    daemon.main()


# It could be called directly or via __init__
if __name__ == "__main__":
    main()
