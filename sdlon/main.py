import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from .config import get_settings
from .fix_departments import FixDepartments
from .log import get_logger
from .metrics import dipex_last_success_timestamp
from .metrics import sd_changed_at_state
from .sd_changed_at import changed_at
from db.queries import delete_last_run
from db.queries import get_status


logger = get_logger()


def create_app(**kwargs) -> FastAPI:
    settings = get_settings(**kwargs)
    settings.job_settings.start_logging_based_on_settings()

    app = FastAPI(
        fix_departments=FixDepartments(settings, settings.sd_institution_identifier)
    )

    # Instrumentation
    sd_changed_at_state.state(get_status().value)
    Instrumentator().instrument(app).expose(app)

    @app.get("/")
    async def index() -> dict[str, str]:
        return {"name": "sdlon"}

    @app.post("/rundb/delete-last-run")
    def rundb_delete_last_run():
        delete_last_run()
        return {"msg": "Last run deleted"}

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
