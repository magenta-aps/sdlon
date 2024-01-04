import enum

from integrations.rundb.db_overview import DBOverview

from sdlon.config import ChangedAtSettings


class RunDBState(enum.Enum):
    RUNNING = "running"
    COMPLETED = "ok"  # Use "ok" instead of "completed" due to the job-runner.sh
    UNKNOWN = "unknown"


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
