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


def get_logger():
    """
    DEPRECATED: will be removed in future commit
    Use this function to get a logger instead of using structlog.get_logger() directly
    """
    return structlog.get_logger()


def setup_logging(log_level: LogLevel) -> None:
    # Disable logging from imported modules that use Pythons stdlib logging
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "default": {
                    "level": log_level.value,
                    "class": "logging.StreamHandler",
                },
                "file": {
                    "level": log_level.value,
                    "class": "logging.handlers.WatchedFileHandler",
                    # Filename will be changed in future commit
                    "filename": "/tmp/hurra.log",
                },
            },
            "loggers": {
                "root": {
                    "handlers": ["default", "file"],
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
