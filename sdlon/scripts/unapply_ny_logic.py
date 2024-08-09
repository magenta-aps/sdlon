# This script "un-applies" the NY-logic, i.e. it will move the engagements
# from MO from their elevations in the NY-levels and back down to the
# "afdelingsniveaer" (see Redmine case #61426)
from collections import namedtuple
from datetime import date
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import click
from more_itertools import first
from more_itertools import one
from sdclient.responses import EmploymentWithLists

from sdlon.log import LogLevel
from sdlon.log import setup_logging
from sdlon.mo import MO
from sdlon.scripts.fix_terminated_engagements import get_sd_employment_map
from sdlon.sd import SD


# We use a named tuple over a Pydantic model since the former is hashable
# (to be used as a dictionary key)
Validity = namedtuple("Validity", ["from_", "to"])


def get_mo_eng_validity_map(
    mo: MO,
    from_date: datetime | None,
    to_date: datetime | None,
    include_org_unit: bool = False,
) -> dict[tuple[str, str], dict[Validity, dict[str, str]]]:
    """
    Get a map like this for the MO engagements:

    {
        (cpr, EmploymentIdentifier): {
            Validity(from_=datetime(...), to=datetime(...)): {
                "eng_uuid": ...,
                "ou_uuid": ...
            }
        },
        ...
    }

    where the SD EmploymentIdentifier is the same as the engagement user_key
    and the key of the inner map is the engagement validity.
    """

    eng_objs = mo.get_engagements(from_date, to_date, include_org_unit=include_org_unit)

    mo_eng_map = dict()
    for obj in eng_objs:
        validities = obj["validities"]

        persons = first(validities)["person"]
        cpr = one(persons)["cpr_number"]
        emp_id = first(validities)["user_key"]

        mo_eng_map[(cpr, emp_id)] = {
            Validity(
                datetime.fromisoformat(validity["validity"]["from"]),
                datetime.fromisoformat(validity["validity"]["to"])
                if validity["validity"]["to"] is not None
                else datetime.max,
            ): {
                "eng_uuid": obj["uuid"],
                "ou_uuid": one(validity["org_unit"])["uuid"],
            }
            for validity in validities
        }

    return mo_eng_map


def get_update_interval(
    mo_validity: Validity,
    sd_activation_date: date,
    sd_deactivation_date: date,
) -> tuple[datetime, datetime | None]:
    assert sd_activation_date <= mo_validity.from_.date()

    end_date: date = min(mo_validity.to.date(), sd_deactivation_date)
    end = datetime(end_date.year, end_date.month, end_date.day)
    end = end if not end.date() == date.max else None

    return mo_validity.from_, end


def update_eng_ou(
    mo: MO,
    sd_ou: UUID,
    mo_ou: UUID,
    cpr_empid: tuple[str, str],
    engagement: UUID,
    update_from: datetime,
    update_to: datetime,
    dry_run: bool,
) -> None:
    if not sd_ou == mo_ou:
        print(f"{cpr_empid[0]}, {cpr_empid[1]}, {str(sd_ou)}, {str(mo_ou)}")
        if not dry_run:
            mo.update_engagement(
                eng_uuid=engagement,
                from_date=update_from,
                to_date=update_to if not update_to.date() == date.max else None,
                org_unit=sd_ou,
            )


def update_engs_ou(
    sd: SD,
    mo: MO,
    sd_map: dict[tuple[str, str], EmploymentWithLists],
    mo_map: dict[tuple[str, str], dict[Validity, dict[str, str]]],
    dry_run: bool,
) -> None:
    """
    Update (if necessary) the engagement OUs in MO according to department
    in SD, i.e. we move the engagements back to the SD "afdelingsniveauer"
    from the "NY-levels" in MO.

    Args:
        sd: the SD client
        mo: the MO client
        sd_map: the SD EmploymentWithLists map (from get_sd_employment_map)
        mo_map: the MO end date map (from get_mo_eng_end_date_map)
        dry_run: if True, do not perform any changes in MO
    """

    for cpr_empID, validity_map in mo_map.items():
        sd_emp = sd_map.get(cpr_empID)
        if sd_emp is None:
            print("Could not find employment in SD")
            continue
        for validity, eng_data in validity_map.items():
            if validity.from_.date() < first(sd_emp.EmploymentDepartment).ActivationDate:
                # Get missing SD intervals
                pass


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

    now = datetime.now(tz=ZoneInfo("Europe/Copenhagen"))

    print("Get SD employments")
    sd_employments = sd.get_sd_employments(now.date())
    sd_employments_changed = sd.get_sd_employments_changed(
        activation_date=now,
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
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()