# This script "un-applies" the NY-logic, i.e. it will move the engagements
# from MO from their elevations in the NY-levels and back down to the
# "afdelingsniveaer" (see Redmine case #61426)
from datetime import date
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import click
from more_itertools import first
from more_itertools import one

from sdlon.log import LogLevel
from sdlon.log import setup_logging
from sdlon.mo import MO
from sdlon.scripts.fix_terminated_engagements import get_sd_employment_map
from sdlon.sd import SD


def get_mo_eng_validity_map(
    mo: MO,
    from_date: datetime | None,
    to_date: datetime | None,
    include_org_unit: bool = False,
) -> dict[tuple[str, str], dict[dict[str, datetime], dict[str, Any]]]:
    """
    Get a map like this for the MO engagements:

    {
        (cpr, EmploymentIdentifier): {
            {
                "from": datetime(...),
                "to": datetime(...)
            }: {
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
            validity["validity"]: {
                "eng_uuid": obj["uuid"],
                "ou_uuid": one(validity["org_unit"])["uuid"],
            }
            for validity in validities
        }

    return mo_eng_map


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


if __name__ == "__main__":
    main()
