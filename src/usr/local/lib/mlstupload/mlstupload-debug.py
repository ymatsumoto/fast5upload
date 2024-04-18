#!/opt/ont/minknow/ont-python/bin/python

# pylint: disable=invalid-name
## As this is a command line tool
import sys

__doc__ = "Check if the daemon can communicate with the server"

def main():
    "Main cmdline invocation"
    if sys.version_info.major == 2:
        print("Bundled python version is 2.")
        print("Python 2 is unsupported. Are you sure that you have upgraded MinKNOW?")
        sys.exit(1)
    try:
        import mlstupload # pylint: disable=import-outside-toplevel
        ## As we need to show the user which one went wrong
    except ModuleNotFoundError as err:
        print("Module",err.name,"not found.")
        print("Please contact support for how to install the missing module.")
        sys.exit(2)

    conf = mlstupload.load_config()
    mlstupload.WebRequest.config_api(conf)
    try:
        with mlstupload.WebRequest() as api:
            resp = api.request(
                "POST",
                "rest/session/info",
                body=mlstupload.up.urlencode({"id": api.token}).encode("ascii"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                }
            )
            user_info = mlstupload.json.loads(resp.data.encode("utf-8"))
    except Exception as err: # pylint: disable=broad-except
        ## As we need to show the user all errors we encountered
        print("Error when trying to login to Server")
        print(err)
        print("Please check your /etc/mlstverse/fast5upload.conf configuration file.")
        sys.exit(3)
    print("Test successful. Welcome,", user_info["name"])

if __name__ == '__main__':
    main()
