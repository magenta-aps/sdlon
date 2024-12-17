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


def setup_logging(
    log_level: LogLevel,
    log_to_file: bool = False,
    log_file: str = "/var/log/sdlon/sd.log",
    log_file_backup_count: int = 90,
) -> None:
    handlers = ["stdout"]
    if log_to_file:
        handlers.append("file")

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "stdout": {
                    "level": log_level.value,
                    "class": "logging.StreamHandler",
                },
                "file": {
                    "level": log_level.value,
                    "class": "logging.handlers.TimedRotatingFileHandler",
                    "filename": log_file,
                    "when": "D",  # Make a new log file each day
                    "utc": True,
                    "backupCount": log_file_backup_count,
                },
            },
            "loggers": {
                "root": {
                    "handlers": handlers,
                    "level": log_level.value,
                    "propagate": True,
                },
                "raclients": {
                    "handlers": handlers,
                    "level": "CRITICAL",
                },
            },
        }
    )

    structlog.configure(
        processors=[
            structlog.processors.CallsiteParameterAdder(
                [CallsiteParameter.MODULE, CallsiteParameter.FUNC_NAME],
            ),
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
