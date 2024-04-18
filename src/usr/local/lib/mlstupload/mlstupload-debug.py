#!/opt/ont/minknow/ont-python/bin/python
import sys

def main():
    if sys.version_info.major == 2:
        print("Bundled python version is 2.")
        print("Python 2 is unsupported. Are you sure that you have upgraded MinKNOW?")
        exit(1)
    try:
        import mlstupload
    except ModuleNotFoundError as e:
        print("Module",e.name,"not found.")
        print("Please contact support for how to install the missing module.")
        exit(2)

    conf = mlstupload.load_config()
    try:
        with mlstupload.WebRequest() as api:
            resp = api.request(
                "POST",
                "rest/session/info",
                body=up.urlencode({"id": api.token}).encode("ascii"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                }
            )
            user_info = json.loads(resp.data.encode("utf-8"))
    except Exception as e:
        print("Error when trying to login to Server")
        print(e)
        print("Please check your /etc/mlstverse/fast5upload.conf configuration file.")
        exit(3)
    print("Test successful. Welcome,", user_info["name"])

main() if __name__ == '__main__' else None
