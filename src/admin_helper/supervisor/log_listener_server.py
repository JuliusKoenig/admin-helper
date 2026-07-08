import json
import socket
from contextlib import contextmanager
from dataclasses import field, dataclass
from pathlib import Path

from admin_helper.supervisor.main import Supervisor
from admin_helper.supervisor.log_listener import SOCKET_FILE_PATH
from admin_helper.objects import ThreadObject


@dataclass
class _SupervisorLogServer(ThreadObject,
                           name="supervisor_log_server",
                           parent=Supervisor):
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

SupervisorLogServer = _SupervisorLogServer()
