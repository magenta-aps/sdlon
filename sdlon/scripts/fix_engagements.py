import re
from datetime import datetime
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import click
from more_itertools import one
from more_itertools import only
from pydantic import ValidationError

from sdlon.log import anonymize_cpr
from sdlon.log import LogLevel
from sdlon.log import setup_logging
from sdlon.mo import MO
from sdlon.sd import SD


REGEX_INT = re.compile("[0-9]{5}")


@click.command()
@click.option(
    "--username",
    "username",
    type=click.STRING,
    envvar="SD_USER",
    required=True,
    help="SD username",
)
@click.option(
    "--password",
    "password",
    type=click.STRING,
    envvar="SD_PASSWORD",
    required=True,
    help="SD password",
)
@click.option(
    "--institution-identifier",
    "institution_identifier",
    type=click.STRING,
    envvar="SD_INSTITUTION_IDENTIFIER",
    required=True,
    help="SD institution identifier",
)
@click.option(
    "--auth-server",
    "auth_server",
    type=click.STRING,
    envvar="AUTH_SERVER",
    default="http://localhost:8090/auth",
    help="Keycloak auth server URL",
)
@click.option(
    "--client-id",
    "client_id",
    type=click.STRING,
    default="dipex",
    envvar="CLIENT_ID",
    help="Keycloak client id",
)
@click.option(
    "--client-secret",
    "client_secret",
    type=click.STRING,
    required=True,
    envvar="CLIENT_SECRET",
    help="Keycloak client secret for the DIPEX client",
)
@click.option(
    "--mo-base-url",
    "mo_base_url",
    type=click.STRING,
    default="http://localhost:5000",
    envvar="MO_URL",
    help="Base URL for calling MO",
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
    readme: bool,
):
    if not readme:
        print("Make sure you have read the README.md before running the script")
        exit(0)

    setup_logging(LogLevel.DEBUG)

    sd = SD(username, password, institution_identifier)
    mo = MO(auth_server, client_id, client_secret, mo_base_url)

    now = datetime.now(tz=ZoneInfo("Europe/Copenhagen"))
    engagements = mo.get_engagements(now, None)

    for count, eng in enumerate(engagements):
        # if count % 100 == 0:
        #     print(f"--- count: {count}")

        eng_uuid = UUID(eng["uuid"])

        for validity in eng["validities"]:
            org_unit = one(validity["org_unit"])
            person = one(validity["person"])

            mo_ou_uuid: str = org_unit["uuid"]
            cpr: str = person["cpr_number"]
            mo_emp_uuid: str = person["uuid"]
            user_key: str = validity["user_key"]
            mo_from_date: datetime = datetime.fromisoformat(
                validity["validity"]["from"]
            )
            mo_to_date: str = validity["validity"]["to"]
            # UUID of the employee who is manager
            managers = only(org_unit["managers"])

            # print(f"Processing {cpr}...")

            if not REGEX_INT.match(user_key):
                continue
            if (
                managers is not None
                and one(managers["employee"])["uuid"] == mo_emp_uuid
            ):
                continue

            lookup_datetime = max(now, mo_from_date + timedelta(days=1))

            try:
                sd_emp_resp = sd.get_sd_employments(
                    effective_date=lookup_datetime.date(),
                    cpr=cpr,
                    employment_identifier=user_key,
                )
                employment = one(one(sd_emp_resp.Person).Employment)
            except (ValidationError, ValueError):
                print(
                    f"{str(mo_emp_uuid)} {anonymize_cpr(cpr)} {user_key} {mo_from_date.isoformat()} {mo_to_date} {mo_ou_uuid} Not found in SD! Terminating"  # noqa
                )
                mo.terminate_engagement(eng_uuid, now)
                print("Terminated")
                continue

            sd_from_date = employment.EmploymentStatus.ActivationDate
            sd_to_date = employment.EmploymentStatus.DeactivationDate
            sd_dep_uuid = employment.EmploymentDepartment.DepartmentUUIDIdentifier

            if not mo_ou_uuid == str(sd_dep_uuid):
                print(
                    f"{str(mo_emp_uuid)} {anonymize_cpr(cpr)} {user_key} {mo_from_date.isoformat()} {mo_to_date} {mo_ou_uuid} {sd_from_date} {sd_to_date} {str(sd_dep_uuid)}"  # noqa
                )
                mo.update_engagement(
                    eng_uuid,
                    mo_from_date,
                    datetime.fromisoformat(mo_to_date)
                    if mo_to_date is not None
                    else None,
                    sd_dep_uuid,
                )
                print("Updated")


if __name__ == "__main__":
    main()
