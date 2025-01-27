# This script will do the following for each active or future active
# engagement in MO:
# * Update the MO unit for the engagement according to the SD department
#   for the corresponding SD employment *no matter what*, i.e. we do not
#   check the engagement unit in MO before updating (the unit may be correct
#   or incorrect in MO)!
# * The script will loop over the *SD department validities* for the engagement
#   while performing the update. This may cause re-opening the engagement (if
#   the the SD department validity exceeds the MO engagement validity), so in some
#   cases we re-terminate the engagement in MO.
from datetime import date
from datetime import datetime
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import click
from more_itertools import first
from more_itertools import last
from sdclient.responses import EmploymentWithLists

from sdlon.log import anonymize_cpr
from sdlon.log import LogLevel
from sdlon.log import setup_logging
from sdlon.mo import MO
from sdlon.scripts.fix_terminated_engagements import get_sd_employment_map
from sdlon.scripts.unapply_ny_logic import get_missing_departments
from sdlon.scripts.unapply_ny_logic import get_mo_eng_validity_map
from sdlon.scripts.unapply_ny_logic import update_eng_ou
from sdlon.scripts.unapply_ny_logic import Validity
from sdlon.sd import SD


def get_mo_eng_holes(validities: list[Validity]) -> list[Validity]:
    start_dates = (validity.from_.date() for validity in validities[1:])
    end_dates = (validity.to.date() for validity in validities[:-1])
    date_pairs = zip(end_dates, start_dates)

    tz = first(validities).from_.tzinfo

    holes = [
        Validity(
            datetime(end_date.year, end_date.month, end_date.day, tzinfo=tz)
            + timedelta(days=1),
            datetime(start_date.year, start_date.month, start_date.day, tzinfo=tz)
            - timedelta(days=1),
        )
        for end_date, start_date in date_pairs
        if end_date + timedelta(days=1) < start_date
    ]

    return holes


def update_engs_ou(
    sd: SD,
    mo: MO,
    sd_map: dict[tuple[str, str], EmploymentWithLists],
    mo_map: dict[tuple[str, str], dict[Validity, dict[str, str]]],
    cpr: str | None,
    dry_run: bool,
) -> None:
    """
    See description in the top of this file.

    Args:
        sd: the SD client
        mo: the MO client
        sd_map: the SD EmploymentWithLists map (from get_sd_employment_map)
        mo_map: the MO end date map (from get_mo_eng_end_date_map)
        cpr: the CPR number
        dry_run: if True, do not perform any changes in MO
    """

    for cpr_empID, validity_map in mo_map.items():
        # If cpr is set, only process the employee belonging to that CPR
        if cpr is not None and cpr_empID[0] != cpr:
            continue

        timeline_holes = get_mo_eng_holes(list(validity_map.keys()))
        if timeline_holes:
            # At the time of writing there are no holes in the timeline (on test)
            print("Holes in engagement timeline", cpr_empID)
            continue

        sd_emp = sd_map.get(cpr_empID)
        eng_data = validity_map[first(validity_map)]
        anonymized_cpr = (
            anonymize_cpr(cpr_empID[0]) if cpr_empID[0] is not None else "None"
        )
        if sd_emp is None:
            print(
                f"{anonymized_cpr}, {cpr_empID[1]}, "
                f"{eng_data['person_uuid']}, Could not find employment in SD"
            )
            continue

        validities = list(validity_map.keys())
        mo_eng_start = first(validities).from_
        mo_eng_end = last(validities).to

        get_missing_departments(
            sd=sd,
            cpr_empID=cpr_empID,
            mo_start=mo_eng_start,
            sd_emp=sd_emp,
        )

        # Update MO unit for engagement according to the SD department no matter what
        # the unit may be (correct or incorrect) in MO
        sd_departments = [
            dep
            for dep in sd_emp.EmploymentDepartment
            if mo_eng_start.date() <= dep.DeactivationDate
        ]

        for dep in sd_departments:
            update_from = datetime(
                dep.ActivationDate.year,
                dep.ActivationDate.month,
                dep.ActivationDate.day,
                0,
                0,
                0,
            )
            update_to = (
                datetime(
                    dep.DeativationDate.year,
                    dep.DeactivationDate.month,
                    dep.DeactivationDate.day,
                    0,
                    0,
                    0,
                )
                if not dep.DeactivationDate == date.max
                else None
            )
            update_eng_ou(
                mo=mo,
                sd_ou=dep.DepartmentUUIDIdentifier,
                eng_data=eng_data,
                update_from=update_from,
                update_to=update_to,
                dry_run=dry_run,
            )

        if mo_eng_end.date() < date.max:
            print("Terminate engagement", eng_data["eng_uuid"], mo_eng_end)
            if not dry_run:
                mo.terminate_engagement(
                    UUID(eng_data["eng_uuid"]),
                    mo_eng_end,
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
@click.option("--cpr", help="Only process engagements belonging to this CPR")
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
    cpr: str | None,
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

    now = datetime.now(tz=ZoneInfo("Europe/Copenhagen"))

    print("Get SD employments")
    sd_employments = sd.get_sd_employments(now.date())
    sd_employments_changed = sd.get_sd_employments_changed(
        activation_date=now + timedelta(days=1),
        deactivation_date=date(9999, 12, 31),
    )
    sd_emp_map = get_sd_employment_map(sd_employments, sd_employments_changed)

    print("Get MO engagements and validities")
    mo_eng_validity_map = get_mo_eng_validity_map(
        mo=mo, from_date=now, to_date=None, include_org_unit=True
    )

    update_engs_ou(
        sd=sd,
        mo=mo,
        sd_map=sd_emp_map,
        mo_map=mo_eng_validity_map,
        cpr=cpr,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
