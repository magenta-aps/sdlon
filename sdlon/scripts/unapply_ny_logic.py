# This script "un-applies" the NY-logic, i.e. it will move the engagements
# from MO from their elevations in the NY-levels and back down to the
# "afdelingsniveaer" (see Redmine case #61426). More precisely, the script
# moves the engagements to the exact units as specified for the corresponding
# departments in SD.
from collections import namedtuple
from datetime import date
from datetime import datetime
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import click
from more_itertools import first
from more_itertools import one
from sdclient.responses import EmploymentWithLists

from sdlon.date_utils import format_date
from sdlon.log import anonymize_cpr
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

        person = one(first(validities)["person"])
        cpr = person["cpr_number"]
        person_uuid = person["uuid"]
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
                "person_uuid": person_uuid,
                "cpr": cpr,
                "emp_id": emp_id,
            }
            for validity in validities
        }

    return mo_eng_map


def get_missing_departments(
    sd: SD,
    cpr_empID: tuple[str, str],
    mo_start: datetime,
    sd_emp: EmploymentWithLists,
) -> None:
    sd_start_date = mo_start.date()
    try:
        first_know_start_date = first(sd_emp.EmploymentDepartment).ActivationDate
    except ValueError:
        return

    while sd_start_date < first_know_start_date:
        emp = sd.get_sd_employments(
            sd_start_date,
            cpr_empID[0],  # CPR
            cpr_empID[1],  # EmploymentIdentifier
        )
        try:
            department = one(one(emp.Person).Employment).EmploymentDepartment
        except ValueError:
            print(
                f"Could not look up employment for {anonymize_cpr(cpr_empID[0])} "
                f"({cpr_empID[1]}) at {format_date(sd_start_date)}"
            )
            return
        assert department is not None
        sd_emp.EmploymentDepartment.insert(0, department)
        sd_start_date = department.DeactivationDate + timedelta(days=1)


def get_update_interval(
    mo_validity: Validity,
    sd_activation_date: date,
    sd_deactivation_date: date,
) -> tuple[datetime, datetime | None]:
    assert (
        sd_activation_date <= mo_validity.from_.date()
    ), f"{format_date(sd_activation_date)} {format_date(mo_validity.from_.date())}"

    end_date: date = min(mo_validity.to.date(), sd_deactivation_date)
    end = datetime(end_date.year, end_date.month, end_date.day)
    mo_end = end if not end.date() == date.max else None

    return mo_validity.from_, mo_end


def update_eng_ou(
    mo: MO,
    sd_ou: UUID,
    eng_data: dict[str, str],
    update_from: datetime,
    update_to: datetime | None,
    dry_run: bool,
) -> None:
    assert (
        update_from.date() <= update_to.date() if update_to is not None else date.max
    ), (str(sd_ou), eng_data["eng_uuid"], update_from, update_to)

    mo_ou = UUID(eng_data["ou_uuid"])
    emp_id = eng_data["emp_id"]
    cpr = eng_data["cpr"]
    person_uuid = eng_data["person_uuid"]

    if not sd_ou == mo_ou:
        print(
            f"{anonymize_cpr(cpr)}, {emp_id}, {person_uuid}, "
            f"{str(sd_ou)}, {str(mo_ou)}, {format_date(update_from)}, "
            f"{format_date(update_to) if update_to is not None else 'None'}"
        )
        if not dry_run:
            mo.update_engagement(
                eng_uuid=UUID(eng_data["eng_uuid"]),
                from_date=update_from,
                to_date=update_to,
                org_unit=sd_ou,
            )


def update_engs_ou(
    sd: SD,
    mo: MO,
    sd_map: dict[tuple[str, str], EmploymentWithLists],
    mo_map: dict[tuple[str, str], dict[Validity, dict[str, str]]],
    cpr: str | None,
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
        cpr: the CPR number
        dry_run: if True, do not perform any changes in MO
    """

    for cpr_empID, validity_map in mo_map.items():
        if cpr is not None and cpr_empID[0] != cpr:
            continue
        sd_emp = sd_map.get(cpr_empID)
        _validity_eng_data = validity_map[first(validity_map)]
        anonymized_cpr = (
            anonymize_cpr(cpr_empID[0]) if cpr_empID[0] is not None else "None"
        )
        if sd_emp is None:
            print(
                f"{anonymized_cpr}, {cpr_empID[1]}, "
                f"{_validity_eng_data['person_uuid']}, Could not find employment in SD"
            )
            continue
        for validity, eng_data in validity_map.items():
            # Add missing SD departments prior to the MO validity from date
            get_missing_departments(
                sd=sd,
                cpr_empID=cpr_empID,
                mo_start=validity.from_,
                sd_emp=sd_emp,
            )
            if cpr is not None:
                print("sd_emp", sd_emp)

            # Ensure the OU in MO is correct in the entire validity interval
            current_validity = validity
            while current_validity.from_.date() <= validity.to.date():
                if cpr is not None:
                    print("current_validity", current_validity)
                try:
                    dep = one(
                        [
                            dep
                            for dep in sd_emp.EmploymentDepartment
                            if dep.ActivationDate
                            <= current_validity.from_.date()
                            <= dep.DeactivationDate
                        ]
                    )
                except ValueError:
                    print(
                        f"{anonymized_cpr}, {cpr_empID[1]}, "
                        f"{_validity_eng_data['person_uuid']}, "
                        f"No EmploymentDepartment found for interval "
                        f"[{format_date(current_validity.from_)}, "
                        f"{format_date(current_validity.to)}]"
                    )
                    break

                update_from, update_to = get_update_interval(
                    current_validity, dep.ActivationDate, dep.DeactivationDate
                )
                update_eng_ou(
                    mo=mo,
                    sd_ou=dep.DepartmentUUIDIdentifier,
                    eng_data=eng_data,
                    update_from=update_from,
                    update_to=update_to,
                    dry_run=dry_run,
                )

                if update_to is None:
                    break

                current_validity = Validity(
                    update_to + timedelta(days=1),
                    validity.to,
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
