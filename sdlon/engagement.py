import re
from datetime import date
from datetime import timedelta
from operator import itemgetter
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import OrderedDict
from typing import Tuple

from integrations.SD_Lon.sdlon.sd_common import EmploymentStatus as EmploymentStatusEnum
from more_itertools import last
from more_itertools import one
from more_itertools import partition
from os2mo_helpers.mora_helpers import MoraHelper
from structlog.stdlib import get_logger

from .date_utils import format_date
from .date_utils import get_mo_validity
from .date_utils import get_sd_validity
from .date_utils import parse_datetime
from .sd_common import ensure_list
from .sd_common import mora_assert
from .sd_common import read_employment_at
from .skip import skip_job_position_id

INTERNAL_EMPLOYEE_REGEX = re.compile("[0-9]+")

logger = get_logger()


def engagement_components(engagement_info) -> Tuple[str, Dict[str, List[Any]]]:
    employment_id = engagement_info["EmploymentIdentifier"]

    return employment_id, {
        "status_list": ensure_list(engagement_info.get("EmploymentStatus", [])),
        "professions": ensure_list(engagement_info.get("Profession", [])),
        "departments": ensure_list(engagement_info.get("EmploymentDepartment", [])),
        "working_time": ensure_list(engagement_info.get("WorkingTime", [])),
    }


def update_existing_engagement(
    sd_updater, mo_engagement, sd_employment, person_uuid
) -> None:
    sd_updater.edit_engagement_department(sd_employment, mo_engagement, person_uuid)
    if sd_updater.settings.sd_overwrite_existing_employment_name:
        sd_updater.edit_engagement_profession(sd_employment, mo_engagement)
    sd_updater.edit_engagement_type(sd_employment, mo_engagement)
    sd_updater.edit_engagement_worktime(sd_employment, mo_engagement)


def create_engagement(
    sd_updater,
    employment_id,
    person_uuid,
    cpr: str,
    sd_lookup_date: date,
) -> None:
    # Call SD to get SD employment
    sd_employment_payload = read_employment_at(
        effective_date=sd_lookup_date,
        settings=sd_updater.settings,
        inst_id=sd_updater.current_inst_id,
        cpr=cpr,
        employment_id=employment_id,
        status_passive_indicator=False,
        dry_run=sd_updater.dry_run,
    )
    if sd_employment_payload is None:
        return

    assert not isinstance(sd_employment_payload, list)

    sd_employment = sd_employment_payload.get("Employment")
    status = sd_employment.get("EmploymentStatus")  # type: ignore

    # Is it possible that sd_employment or status is None?...
    assert sd_employment
    assert status

    # Not sure what to do if several statuses are returned...
    assert not isinstance(status, list)

    # Call MO to create corresponding engagement in MO
    sd_updater.create_new_engagement(sd_employment, status, cpr, person_uuid)


def _is_external(employment_id: str) -> bool:
    """
    Check if the SD employee is an external employee. This is the
    case (at least in some municipalities...) if the EmploymentIdentifier
    contains letters.

    Args:
         employment_id: the SD EmploymentIdentifier

    Returns:
        True of the employment_id contains letters and False otherwise
    """

    match = INTERNAL_EMPLOYEE_REGEX.match(employment_id)
    return match is None


def is_employment_id_and_no_salary_minimum_consistent(
    engagement: OrderedDict, no_salary_minimum: Optional[int] = None
) -> bool:
    """
    Check that the external SD employees have JobPositionIdentifiers
    consistent with no_salary_limit
    (see https://os2web.atlassian.net/browse/MO-245).

    Args:
        engagement: the SD employment
        no_salary_minimum: the minimum allowed JobPositionIdentifier
          for external SD employees.

    Returns:
        True if the provided values are consistent and False otherwise.
    """

    if no_salary_minimum is None:
        return True

    employment_id, eng_components = engagement_components(engagement)
    professions = eng_components["professions"]
    if not professions:
        return True

    job_pos_ids_strings = map(itemgetter("JobPositionIdentifier"), professions)
    job_pos_ids = map(int, job_pos_ids_strings)

    def is_consistent(job_pos_id: int) -> bool:
        if _is_external(employment_id):
            return job_pos_id >= no_salary_minimum  # type: ignore
        return job_pos_id < no_salary_minimum  # type: ignore

    consistent = map(is_consistent, job_pos_ids)

    return all(consistent)


def filtered_professions(
    sd_employment: OrderedDict, job_pos_ids_to_skip: list[str]
) -> OrderedDict:
    """
    Remove any professions with a JobPositionIdentifier in the
    job_pos_ids_to_skip list (provided via the setting sd_skip_employment_types
    or the environment variable SD_SKIP_EMPLOYMENT_TYPES).

    Args:
        sd_employment: the SD employment
        job_pos_ids_to_skip: list of JobPositionIdentifiers to remove from
          "Professions" in the SD employment payload

    Returns:
        The SD employment payload where the professions to be skipped
        are removed.
    """

    professions = ensure_list(sd_employment.get("Profession", []))
    sd_employment["Profession"] = [
        profession
        for profession in professions
        if not skip_job_position_id(profession, job_pos_ids_to_skip)
    ]

    return sd_employment


def has_active_status(emp_status: dict[str, str]) -> bool:
    return emp_status["EmploymentStatusCode"] in (
        status.value for status in EmploymentStatusEnum.employeed()
    )


def get_last_day_of_sd_work(emp_status_list: list[dict[str, str]]) -> date | None:
    inactive_emp_statuses_gen, active_emp_statuses_gen = partition(
        has_active_status, emp_status_list
    )
    active_emp_statuses = list(active_emp_statuses_gen)
    inactive_emp_statuses = list(inactive_emp_statuses_gen)

    if active_emp_statuses:
        # This will not handle the (possible but unlikely) situation where active
        # (status 0, 1 and 3) and passive (status 8, 9 and S) SD statuses are mixed,
        # e.g.
        # |------ 1 ------|--- 8 ---|---- 1 ----|----- 8 -----
        return parse_datetime(last(active_emp_statuses)["DeactivationDate"]).date()

    if inactive_emp_statuses:
        # First day of non-work (e.g. retirement (status 8))
        activation_date = parse_datetime(
            one(inactive_emp_statuses)["ActivationDate"]
        ).date()
        # Last day of work
        return activation_date - timedelta(days=1)

    return None


def get_eng_user_key(
    sd_emp_id: str,
    sd_inst_id: str,
    prefix_eng_user_key_with_inst_id: bool,
) -> str:
    """
    Get the effective MO engagement user_key. Ideally, we should use a combined
    state/strategy pattern here, but for now we will just use a parametric switch
    based on the application settings.

    Args:
        sd_emp_id: the SD EmploymentIdentifier
        sd_inst_id: the SD InstitutionIdentifier
        prefix_eng_user_key_with_inst_id: if True, the user_key will be prefixed with
          the SD InstitutionIdentifier

    Returns:
        The MO engagement user_key, e.g "12345" or "AB-12345"
    """

    # This block was adapted from SDChangedAt._find_engagement. This is problematic if
    # there exist cases where sd_emp_id is 6 figures.
    try:
        user_key = str(int(sd_emp_id)).zfill(5)
    except ValueError:
        user_key = sd_emp_id

    if not prefix_eng_user_key_with_inst_id:
        return user_key
    return f"{sd_inst_id.upper()}-{user_key}"


def terminate_eng_from_uuid(
    mora_helper: MoraHelper,
    eng_uuid: str,
    dry_run: bool,
    from_date: str,
    to_date: str | None = None,
) -> None:
    validity = {"from": from_date, "to": to_date}

    payload = {
        "type": "engagement",
        "uuid": eng_uuid,
        "validity": validity,
    }

    logger.debug("Terminate payload (details/terminate)", payload=payload)
    if not dry_run:
        response = mora_helper._mo_post("details/terminate", payload)
        logger.debug("Terminate response: {}".format(response.text))
        mora_assert(response)


def re_terminate_engagement(
    mora_helper: MoraHelper,
    mo_eng: dict[str, Any],
    eng_info_obj: dict[str, Any],
    emp_status_list: list[dict[str, str]],
    dry_run: bool,
) -> None:
    """
    We re-terminate an engagement, if it was terminated before an edit
    operation, since the edit operation re-opens any previously terminated
    engagements (since we are no longer using "cut" dates when generating
    the MO validity). See details here:
    https://redmine.magenta.dk/issues/60402#note-16 and
    https://redmine.magenta.dk/issues/61683

    Args:
        mora_helper: the MoRaHelper instance
        mo_eng: the MO engagement
        eng_info_obj: the engagement_info object
        emp_status_list: the SD payload EmploymentStatus objects
        dry_run: whether we are performing a dry run or not
    """

    def terminate_eng(eng_end: date) -> None:
        # We need to add 1 day to the "last day of work" to get the "first day of
        # non-work", i.e. the first day of the termination period.
        term_start_date = eng_end + timedelta(days=1)
        term_start: str = format_date(term_start_date)

        logger.debug(
            "Re-terminate engagement",
            eng_uuid=mo_eng["uuid"],
            term_start_date=term_start,
        )

        terminate_eng_from_uuid(mora_helper, mo_eng["uuid"], dry_run, term_start)

    # The MO engagement validity of the (time line wise) latest engagement.
    mo_validity = get_mo_validity(mo_eng)
    # The SD payload validity
    sd_validity = get_sd_validity(eng_info_obj)

    last_day_of_sd_work = get_last_day_of_sd_work(emp_status_list)
    if last_day_of_sd_work is not None:
        # If we enter this if-block, the SD payload contains one or more
        # EmploymentStatus objects and hence the validity of the engagement in MO
        # could have changed.
        eng_end_date = max(mo_validity["to"], last_day_of_sd_work)
        logger.debug(
            "EmploymentStatus changes - we may need to terminate",
            eng_end_date=format_date(eng_end_date),
        )
        if sd_validity["to"] > eng_end_date:
            terminate_eng(eng_end_date)
        return

    if sd_validity["to"] > mo_validity["to"]:
        terminate_eng(mo_validity["to"])
