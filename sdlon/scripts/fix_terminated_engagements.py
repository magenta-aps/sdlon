# This script adds or re-opens the terminated engagements described
# in Redmine case #61415.
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import click
from more_itertools import first
from more_itertools import last
from more_itertools import one
from sdclient.responses import Employment
from sdclient.responses import EmploymentWithLists
from sdclient.responses import GetEmploymentChangedResponse
from sdclient.responses import GetEmploymentResponse

from sdlon.date_utils import format_date
from sdlon.date_utils import SD_INFINITY
from sdlon.log import get_logger
from sdlon.log import LogLevel
from sdlon.log import setup_logging
from sdlon.mo import MO
from sdlon.sd import SD
from sdlon.sd_common import EmploymentStatus as EmploymentStatusEnum

logger = get_logger()


def get_emp_status_timeline(
    employment: Employment, employment_changed: EmploymentWithLists | None
) -> EmploymentWithLists:
    # TODO: for now, we only handle EmploymentStatus. In the future we
    #       should also handle Profession and EmploymentDepartment

    # The EmploymentIdentifiers must match
    if employment_changed is not None:
        assert (
            employment.EmploymentIdentifier == employment_changed.EmploymentIdentifier
        )

    future_emp_statuses = (
        employment_changed.EmploymentStatus
        if employment_changed is not None
        and employment_changed.EmploymentStatus is not None
        else []
    )
    # Only include active SD employments
    future_emp_statuses = [
        emp_status
        for emp_status in future_emp_statuses
        if emp_status.EmploymentStatusCode
        in (status.value for status in EmploymentStatusEnum.employeed())
    ]

    emp_timeline = EmploymentWithLists(
        EmploymentIdentifier=employment.EmploymentIdentifier,
        EmploymentDate=employment.EmploymentDate,
        AnniversaryDate=employment.AnniversaryDate,
        EmploymentStatus=[employment.EmploymentStatus] + future_emp_statuses,
    )

    if len(emp_timeline.EmploymentStatus) <= 1:
        return emp_timeline

    # Make sure there are no holes in the timeline, i.e. we make sure that
    # the DeactivationDate for EmploymentStatus object number n is exactly
    # one day earlier than the ActivationDate for EmploymentStatus object
    # number n + 1
    activation_dates = (
        emp_status.ActivationDate for emp_status in emp_timeline.EmploymentStatus[1:]
    )
    deactivation_dates = (
        emp_status.DeactivationDate for emp_status in emp_timeline.EmploymentStatus[:-1]
    )
    date_pairs = zip(activation_dates, deactivation_dates)
    assert all(
        deactivation_date + timedelta(days=1) == activation_date
        for activation_date, deactivation_date in date_pairs
    )

    return emp_timeline


def get_sd_employment_map(
    sd_employments: GetEmploymentResponse,
    sd_employments_changed: GetEmploymentChangedResponse,
) -> dict[tuple[str, str], EmploymentWithLists]:
    """
    Get a map from (cpr, EmploymentIdentifier) to the corresponding employment
    status timeline.

    Args:
        sd_employments: the response from SD GetEmployment
        sd_employments_changed: the response from SD GetEmploymentChanged

    Returns:
        map from (cpr, EmploymentIdentifier) to the corresponding employment
        status timeline.
    """

    def get_map(
        sd_emp: GetEmploymentResponse | GetEmploymentChangedResponse,
    ) -> dict[tuple[str, str], Employment | EmploymentWithLists]:
        return {
            (person.PersonCivilRegistrationIdentifier, emp.EmploymentIdentifier): emp
            for person in sd_emp.Person
            for emp in person.Employment
        }

    sd_emp_map = get_map(sd_employments)
    sd_emp_changed_map = get_map(sd_employments_changed)

    return {
        key: get_emp_status_timeline(emp, sd_emp_changed_map.get(key))
        for key, emp in sd_emp_map.items()
    }


def get_mo_eng_validity_map(mo: MO) -> dict[tuple[str, str], dict[str, Any]]:
    """
    Get the validity of the last validity in the list of the engagement
    validities in the GraphQL response from MO.
    """
    eng_objs = mo.get_engagements(None, None)

    mo_eng_map = dict()
    for obj in eng_objs:
        validities = obj["validities"]

        persons = first(validities)["person"]
        cpr = one(persons)["cpr_number"]
        emp_id = first(validities)["user_key"]

        from_ = last(validities)["validity"]["from"]
        to = last(validities)["validity"]["to"]

        mo_eng_map[(cpr, emp_id)] = {
            "eng_uuid": obj["uuid"],
            "from": datetime.fromisoformat(from_),
            "to": datetime.fromisoformat(to)
            if to is not None
            else datetime.max,  # 9999-12-31 23:59:59.999999
        }

    return mo_eng_map


def update_engagements(
    mo: MO,
    sd_map: dict[tuple[str, str], EmploymentWithLists],
    mo_map: dict[tuple[str, str], dict[str, Any]],
    dry_run: bool,
) -> None:
    """
    Fixes the engagements in MO that have been terminated by mistake.

    Args:
        mo: the MO client
        sd_map: the SD EmploymentWithLists map (from get_sd_employment_map)
        mo_map: the MO end date map (from get_mo_eng_end_date_map)
        dry_run: if True, do not perform any changes in MO
    """

    # sd_end_dates = dict()
    for cpr_emp_id, emp_w_lists in sd_map.items():
        if cpr_emp_id not in mo_map:
            continue

        sd_end_date: date = last(emp_w_lists.EmploymentStatus).DeactivationDate
        mo_end_date: datetime = mo_map[cpr_emp_id]["to"]
        eng_uuid = UUID(mo_map[cpr_emp_id]["eng_uuid"])

        if sd_end_date == mo_end_date.date():
            continue

        if sd_end_date < mo_end_date.date():
            # Terminate engagement in MO
            print(
                cpr_emp_id[0],
                cpr_emp_id[1],
                sd_end_date,
                mo_end_date.date(),
                "Terminate engagement",
            )
            if not dry_run:
                mo.terminate_engagement(
                    eng_uuid,
                    datetime(
                        sd_end_date.year, sd_end_date.month, sd_end_date.day, 0, 0, 0
                    ),
                )
        elif sd_end_date > mo_end_date.date():
            # Update engagement in MO
            print(
                cpr_emp_id[0],
                cpr_emp_id[1],
                sd_end_date,
                mo_end_date.date(),
                "Update engagement",
            )
            if not dry_run:
                mo.update_engagement_dates(
                    eng_uuid,
                    mo_map[cpr_emp_id]["from"],
                    datetime(
                        sd_end_date.year, sd_end_date.month, sd_end_date.day, 0, 0, 0
                    )
                    if not format_date(sd_end_date) == SD_INFINITY
                    else None,
                )


@click.command()
@click.option("--username", envvar="SD_USER", required=True, help="SD username")
@click.option("--password", envvar="SD_PASSWORD", required=True, help="SD password")
@click.option(
    "--institution-identifier",
    envvar="SD_INSTITUTION_IDENTIFIER",
    required=True,
    help="SD institution identifier",
)
@click.option(
    "--auth-server",
    envvar="AUTH_SERVER",
    default="http://keycloak:8080/auth",
    help="Keycloak auth server URL",
)
@click.option("--client-id", default="developer", help="Keycloak client id")
@click.option(
    "--client-secret",
    required=True,
    help="Keycloak client secret for the 'developer' client",
)
@click.option(
    "--mo-base-url",
    default="http://mo:5000",
    envvar="MO_URL",
    help="Base URL for calling MO",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Do not perform any changes is MO",
)
@click.option(
    "--i-have-read-the-readme",
    "readme",
    is_flag=True,
    help="Set flag to ensure that you have read the readme",
)
def main(
    username: str,
    password: str,
    institution_identifier: str,
    auth_server: str,
    client_id: str,
    client_secret: str,
    mo_base_url: str,
    dry_run: bool,
    readme: bool,
):
    if not readme:
        print(
            "Make sure you have read the sdlon/scripts/README.md before "
            "running this script"
        )
        exit(0)

    setup_logging(LogLevel.DEBUG)

    sd = SD(username, password, institution_identifier)
    mo = MO(auth_server, client_id, client_secret, mo_base_url)

    now = datetime.now(tz=ZoneInfo("Europe/Copenhagen")).date()

    print("Get SD employments")
    sd_employments = sd.get_sd_employments(now)
    sd_employments_changed = sd.get_sd_employments_changed(
        activation_date=now,
        deactivation_date=date(9999, 12, 31),
    )

    sd_emp_map = get_sd_employment_map(sd_employments, sd_employments_changed)
    print("Get MO engagements and validities")
    mo_eng_validity_map = get_mo_eng_validity_map(mo)

    update_engagements(mo, sd_emp_map, mo_eng_validity_map, dry_run)


if __name__ == "__main__":
    main()
