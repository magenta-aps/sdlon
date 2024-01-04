import enum

from integrations.rundb.db_overview import DBOverview
from prometheus_client import Enum
from prometheus_client import Gauge

from sdlon.config import ChangedAtSettings


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


def get_run_db_state(settings: ChangedAtSettings) -> RunDBState:
    try:
        run_db = settings.sd_import_run_db
        db_overview = DBOverview(run_db)
        status_line = db_overview._read_last_line("status")

        if "Running since" in status_line:
            return RunDBState.RUNNING
        if "Update finished" in status_line:
            return RunDBState.COMPLETED
        return RunDBState.UNKNOWN
    except Exception:
        return RunDBState.UNKNOWN
