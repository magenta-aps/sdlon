import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Enum
from prometheus_client import Gauge
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from .config import get_changed_at_settings
from .fix_departments import FixDepartments
from .log import get_logger
from .metrics import get_run_db_state
from .metrics import RunDBState
from .sd_changed_at import changed_at


logger = get_logger()


def create_app(**kwargs) -> FastAPI:
    settings = get_changed_at_settings(**kwargs)
    settings.job_settings.start_logging_based_on_settings()

    app = FastAPI(fix_departments=FixDepartments(settings))

    # Instrumentation

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
    sd_changed_at_state.state(get_run_db_state(settings).value)
    Instrumentator().instrument(app).expose(app)

    @app.get("/")
    async def index() -> dict[str, str]:
        return {"name": "sdlon"}

    @app.post("/trigger")
    async def trigger() -> dict[str, str]:
        loop = asyncio.get_running_loop()
        loop.call_soon(changed_at, dipex_last_success_timestamp, sd_changed_at_state)
        return {"msg": "SD-changed-at started in background"}

    @app.post("/trigger/apply-ny-logic/{ou}")
    async def fix_departments(
        ou: UUID, request: Request, response: Response
    ) -> dict[str, str]:
        logger.info("Triggered fix_department", ou=str(ou))

        today = datetime.today().date()
        fix_departments = request.app.extra["fix_departments"]

        try:
            fix_departments.fix_NY_logic(str(ou), today)
            return {"msg": "success"}
        except Exception as err:
            logger.exception("Error calling fix_department or fix_NY_logic", err=err)
            response.status_code = HTTP_500_INTERNAL_SERVER_ERROR
            return {"msg": str(err)}

    return app
