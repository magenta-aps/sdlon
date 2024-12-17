import logging.config
import re
from enum import Enum

import structlog
from structlog.processors import CallsiteParameter

CPR_REGEX = re.compile("[0-9]{10}")


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def anonymize_cpr(cpr: str) -> str:
    assert CPR_REGEX.match(cpr)
    return cpr[:6] + "xxxx"


# Taken from SDTool+
def _dont_log_graphql_responses(logger, method_name, event_dict) -> dict:
    """Drop logs from `BaseHTTPXTransport._decode_response` (in
    `raclients.graph.transport`), which logs *all* GraphQL responses at DEBUG level.
    (https://git.magenta.dk/rammearkitektur/ra-clients/-/blob/master/raclients/graph/transport.py#L117)
    """
    module: str | None = event_dict.get("module")
    func_name: str | None = event_dict.get("func_name")
    if module == "transport" and func_name in (
        "_decode_response",
        "_construct_payload",
    ):
        raise structlog.DropEvent
    return event_dict


def setup_logging(
    log_level: LogLevel,
    log_to_file: bool = False,
    log_file: str = "/var/log/sdlon/sd.log",
    log_file_backup_count: int = 90,
) -> None:
    file_handler_conf = {
        "level": log_level.value,
        "class": "logging.handlers.TimedRotatingFileHandler",
        "filename": log_file,
        "when": "D",
        "utc": True,
        "backupCount": log_file_backup_count,
    }
    handlers_conf = {
        "stdout": {
            "level": log_level.value,
            "class": "logging.StreamHandler",
        },
    }
    handlers = ["stdout"]

    if log_to_file:
        handlers_conf["file"] = file_handler_conf  # type: ignore
        handlers.append("file")

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": handlers_conf,
            "loggers": {
                "root": {
                    "handlers": handlers,
                    "level": log_level.value,
                    "propagate": True,
                },
            },
        }
    )

    structlog.configure(
        processors=[
            structlog.processors.CallsiteParameterAdder(
                [CallsiteParameter.MODULE, CallsiteParameter.FUNC_NAME],
            ),
            _dont_log_graphql_responses,  # type: ignore
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
