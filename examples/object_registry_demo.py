# ---------------------------------------------------------------------------
# Generic example object definitions
# ---------------------------------------------------------------------------
import logging
from pathlib import Path
from typing import Any

from rich.logging import RichHandler

from admin_helper.console import AdminHelperConsole
from admin_helper.objects.config import (
    LoggerConfigValue,
    ObjectLoggerContexts,
    LoggerContextConfig,
)
from admin_helper.objects.field import field, computed_field, fields
from admin_helper.objects.helper import register
from admin_helper.objects.logger import MaskedValueFilter, Formatter
from admin_helper.objects.object import (
    ObjectLogger,
    ObjectLoggerConfig,
    LoggerParent,
    BaseObject,
    object_registry,
)


# Registration messages are emitted before object instances and their handlers
# exist. The example therefore configures Python's root logger first so those
# early framework messages are visible as well. In a real application this
# belongs in the executable entry point before importing object-definition
# modules.
def _configure_example_bootstrap_logging() -> None:
    """
    Configure bootstrap console logging for the executable example.

    :return:
        Returns None.
    """

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if any(
        handler.get_name() == "example-bootstrap-console"
        for handler in root_logger.handlers
    ):
        return

    console_handler = RichHandler(
        console=AdminHelperConsole,
        show_time=True,
        markup=True,
        show_level=True,
        show_path=False,
    )
    console_handler.set_name("example-bootstrap-console")
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(Formatter("%(message)s"))
    console_handler.addFilter(MaskedValueFilter(None, "console"))
    root_logger.addHandler(console_handler)


_EXAMPLE_LOG_DIRECTORY = Path("logs")
_EXAMPLE_LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

_configure_example_bootstrap_logging()


class WorkerObjectLogger(ObjectLogger):
    """Example custom logger used by one concrete service object."""

    def task_event(self, message: str, *args: Any, **context_values: Any) -> None:
        """
        Emit a worker-specific message inside the ``task.event`` context.

        :param message:
            The log message format string.

        :param args:
            Positional values interpolated into the message.

        :param context_values:
            Additional values exposed through the logging context.

        :return:
            Returns None.
        """

        with self.context("task.event", **context_values):
            self.info(message, *args)


@register(
    name="application",
    kwargs={
        "logger_config": ObjectLoggerConfig(
            parent=LoggerParent.NONE,
            level=logging.DEBUG,
            console_level=LoggerConfigValue.AUTO,
            file_level=LoggerConfigValue.AUTO,
            format=LoggerConfigValue.AUTO,
            console_format=LoggerConfigValue.AUTO,
            file_format=LoggerConfigValue.AUTO,
            show_time=True,
            show_level=True,
            show_name=True,
            show_status=True,
            show_context=True,
            show_context_data=True,
            console=True,
            file=True,
            file_path=_EXAMPLE_LOG_DIRECTORY / "application.log",
            contexts=ObjectLoggerContexts(
                {
                    "task.event": LoggerContextConfig(
                        level=logging.INFO,
                        console_format="[TASK] %(message)s",
                        file_format=(
                            "%(asctime)s [TASK] %(name)s: "
                            "%(message)s | %(log_context_data)s"
                        ),
                    )
                }
            ),
        )
    },
)
class Application(BaseObject):
    """Root object using the central console and application log file."""

    environment: str = field(
        display=True,
        kw_only=True,
        read_only=True,
        default="development",
        title="Environment",
        description="Runtime environment of the application.",
    )


@register(
    name="database",
    parent=Application,
    kwargs={
        "host": "database.example.org",
        "port": 5432,
        "username": "admin",
        "password": "super-secret-password",
        "optional_token": None,
    },
)
class DatabaseService(BaseObject):
    """Service demonstrating display, masked, read-only, and internal fields."""

    host: str = field(
        display=True,
        title="Database host",
        description="Hostname or IP address of the database server.",
    )
    port: int = field(
        display=True,
        title="Database port",
        description="TCP port used for database connections.",
    )
    username: str = field(
        display=True,
        title="Database user",
        description="User name used to authenticate to the database.",
    )
    password: str = field(
        display=True,
        masked=True,
        title="Database password",
        description="Secret used to authenticate the database user.",
    )
    optional_token: str | None = field(
        display=True,
        masked=True,
        empty_values=("unset", "disabled"),
        default=None,
        title="Optional token",
        description="Optional secondary credential.",
    )
    service_id: str = field(
        display=True,
        read_only=True,
        default="database-primary",
        title="Service identifier",
        description="Stable identifier assigned during construction.",
    )
    _connection_attempts: int = field(
        internal=True,
        default=0,
        title="Connection attempts",
        description="Internal connection-attempt counter.",
    )

    @computed_field(
        display=True,
        title="Database endpoint",
        description="Computed host and port used for connections.",
    )
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    @computed_field(
        masked=True,
        title="Connection credential",
        description="Computed credential string used by a connector.",
        as_property=False,
    )
    def connection_credential(self) -> str:
        return f"{self.username}:{self.password}"

    def connect(self) -> None:
        """Log one example operation without exposing the password."""

        self._connection_attempts += 1
        self.logger.info("Connecting %s to '%s:%d'.", self, self.host, self.port)


@register(
    name="worker",
    parent=Application,
    kwargs={
        "queue": "default",
        "access_token": "worker-access-token",
        "logger_config": ObjectLoggerConfig(
            logger_class=WorkerObjectLogger,
            file=True,
            file_path=_EXAMPLE_LOG_DIRECTORY / "worker.log",
            contexts=ObjectLoggerContexts(
                {
                    "task.event": LoggerContextConfig(
                        level=logging.DEBUG,
                        console_level=logging.INFO,
                        file_level=logging.DEBUG,
                        console_format="[WORKER TASK] %(message)s",
                        file_format=(
                            "%(asctime)s [%(levelname)s] "
                            "[%(log_context)s] %(name)s: "
                            "%(message)s | %(log_context_data)s"
                        ),
                    )
                }
            ),
        ),
    },
)
class WorkerService(BaseObject):
    """Service using a dedicated logger class and an additional file handler."""

    queue: str = field(
        display=True, title="Queue", description="Queue consumed by the worker."
    )
    access_token: str = field(
        masked=True, title="Access token", description="Credential used by the worker."
    )
    _processed_tasks: int = field(
        internal=True,
        default=0,
        title="Processed tasks",
        description="Internal number of processed tasks.",
    )

    def process_task(self, task_name: str) -> None:
        """
        Process one example task and emit a contextual logger message.

        :param task_name:
            The human-readable task name.

        :return:
            Returns None.
        """

        self._processed_tasks += 1
        if isinstance(self.logger, WorkerObjectLogger):
            self.logger.task_event(
                "Processing task '%s' with %s.",
                task_name,
                self,
                task_name=task_name,
                processed_tasks=self._processed_tasks,
            )


if __name__ == "__main__":
    object_registry.instantiate_all()

    application = object_registry.get_by_name("application", Application)
    database = object_registry.get_by_name("database", DatabaseService)
    worker = object_registry.get_by_name("worker", WorkerService)

    # ``display_field`` values appear in the concise object representation.
    # ``masked_field`` values only reveal whether they are set.
    print(application)
    print(database)
    print(worker)

    # Query stored and computed fields through one interface.
    print(fields(database, display=True))
    print(fields(DatabaseService, masked=True))

    # ``endpoint`` is an automatically created property. The masked computed
    # field keeps explicit call semantics because ``as_property=False``.
    print(database.endpoint)
    # The callable computed field remains available explicitly. Do not print
    # sensitive computed values unless they are intentionally sanitized.
    # credential = database.connection_credential()

    # Expected output resembles:
    # Application(name='application', environment='development')
    # DatabaseService(name='application.database', host='database.example.org',
    #                 port=5432, username='admin', password=<MASKED>,
    #                 optional_token=<NOT SET>, service_id='database-primary')
    # WorkerService(name='application.worker', queue='default',
    #               access_token=<MASKED>)

    database.connect()
    worker.process_task("refresh-cache")

    # The defensive masking filter also protects accidental direct logging.
    database.logger.warning("The configured password is '%s'.", database.password)

    # ``internal_field`` is framework/private state. It is intentionally absent
    # from the generated constructor, dataclass repr, and BaseObject.__str__.
    # Internal field names must start with an underscore; @register validates
    # this convention. Python still allows deliberate access to the attribute,
    # but the underscore marks it as unsupported external API.
    # print(database._connection_attempts)

    # ``read_only_field`` accepts its initial value but rejects reassignment
    # after initialization. Uncomment this line to see the protection:
    # database.service_id = "replacement-id"

    # Field-specific empty values augment the global defaults. Here both
    # ``'unset'`` and ``'disabled'`` would be represented as <NOT SET>.
    database.optional_token = "unset"
    print(database)

    print()
