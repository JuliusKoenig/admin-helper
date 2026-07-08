import json
import os
import socket
import sys
from pathlib import Path

from supervisor import childutils

os.environ["ADMIN_HELPER_LOGGER__DISABLED"] = "1"  # disable all logging

from admin_helper.settings import RUN_DIRECTORY

SOCKET_FILE_PATH = (RUN_DIRECTORY / "supervisord" / f"{Path(__file__).with_suffix("").name}.sock").absolute()


def send(event: dict):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(SOCKET_FILE_PATH))
            event_data = (json.dumps(event) + "\n")
            sock.sendall(event_data.encode())
    except Exception as e:
        print(f"Failed to send event:\n"
              f"event={event}\n"
              f"error={e.__class__.__name__}({e})", file=sys.stderr, flush=True)


def main():
    try:
        while True:
            headers, payload = childutils.listener.wait(sys.stdin,
                                                        sys.stdout)
            payload_headers, data = childutils.eventdata(payload)
            send({"process": payload_headers["processname"],
                  "group": payload_headers["groupname"],
                  "channel": payload_headers["channel"],
                  "pid": payload_headers["pid"],
                  "message": data.rstrip()})
            childutils.listener.ok(sys.stdout)
    except KeyboardInterrupt:
        ...


if __name__ == "__main__":
    main()
