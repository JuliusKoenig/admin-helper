import json
import os
import socket
import sys
from contextlib import contextmanager
from dataclasses import field, dataclass
from pathlib import Path

from supervisor import childutils

os.environ["ADMIN_HELPER_LOGGER__DISABLED"] = "1"  # disable all logging
from admin_helper.settings import RUN_DIRECTORY
from admin_helper.types.thread_object import ThreadObject

SOCKET_FILE_PATH = (RUN_DIRECTORY / "supervisord" / f"{Path(__file__).with_suffix("").name}.sock").absolute()


@dataclass
class SupervisorLogServer(ThreadObject):
    socket_file_path: Path = field(default=SOCKET_FILE_PATH)

    __str_name__: str | None = "SupervisorLogServer"

    def __post_init__(self):
        if not isinstance(self.socket_file_path, Path):
            self.socket_file_path = Path(self.socket_file_path)
        super().__post_init__()

    @contextmanager
    def socket(self):
        if self.socket_file_path.exists():
            self.socket_file_path.unlink()
        self.socket_file_path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_file_path))
            server.listen()
            yield server

        finally:
            server.close()
            try:
                self.socket_file_path.unlink()
            except FileNotFoundError:
                pass

    def run(self):
        with self.socket() as sock:
            conn, _ = sock.accept()
            with conn:
                file = conn.makefile("r")
                for line in file:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        self.logger.warning("Invalid JSON: %r", line)
                        continue
                    process_name = event["process"]
                    channel_name = event["channel"]
                    message = event["message"]
                    extra = {
                        "process_name": process_name,
                        "channel_name": channel_name,
                    }
                    self.logger.info(message, extra=extra)


def send(event: dict):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(SOCKET_FILE_PATH))
            event_data = (json.dumps(event) + "\n")
            sock.sendall(event_data.encode())
    except Exception as e:
        print(f"Failed to send event: {e}", file=sys.stderr, flush=True)


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
