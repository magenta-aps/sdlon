import enum

from prometheus_client import Enum
from prometheus_client import Gauge


class RunDBState(enum.Enum):
    RUNNING = "running"
    COMPLETED = "ok"  # Use "ok" instead of "completed" due to the job-runner.sh
    UNKNOWN = "unknown"


# TODO: import from fastramqpi.metrics instead, when we switch to using this project.
#   We avoid importing it for now due to potential Poetry conflicts
dipex_last_success_timestamp = Gauge(
    name="dipex_last_success_timestamp",
    documentation="When the integration last successfully ran",
    unit="seconds",
)
sd_changed_at_state = Enum(
    name="sd_changed_at_state",
    documentation="Reflecting the RunDB state",
    states=[state.value for state in RunDBState],
)
