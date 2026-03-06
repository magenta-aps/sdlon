# (this script is copied from fix_status8.py and modified)
# Find all passive employments in SD and ensure that the corresponding
# engagements in MO are terminated accordingly. The script will:
# 1) Get all status 8 employments from SD
# 2) Iterate over these and terminate the corresponding active engagements in MO
from datetime import date
from datetime import datetime
from typing import Any
from typing import List
from uuid import UUID

import click
from gql import gql
from more_itertools import last
from more_itertools import one
from more_itertools import only
from raclients.graph.client import GraphQLClient
from ramodels.mo import employee
from ramodels.mo.employee import Employee
from sdclient.client import SDClient
from sdclient.requests import GetEmploymentChangedRequest
from sdclient.responses import GetEmploymentChangedResponse

from sdlon.date_utils import format_date
from sdlon.graphql import get_mo_client
from sdlon.log import anonymize_cpr
from sdlon.log import LogLevel
from sdlon.log import setup_logging


def get_sd_employment_changed(
    username: str,
    password: str,
    institution_identifier: str,
    cpr: str,
    employment_identifier: str,
) -> GetEmploymentChangedResponse:
    """
    Get all employments from SD (the query params are very
    specific for what is needed here).

    Args:
        username: the username for the SD API
        password: the password for the SD API
        institution_identifier: the SD institution identifier
        cpr: the person CPR
        employment_identifier: the SD employment identifier

    Returns:
        The SD employment
    """

    sd_client = SDClient(username, password)
    sd_employment = sd_client.get_employment_changed(
        GetEmploymentChangedRequest(
            InstitutionIdentifier=institution_identifier,
            PersonCivilRegistrationIdentifier=cpr,
            EmploymentIdentifier=employment_identifier,
            ActivationDate=date(1900, 1, 1),
            DeactivationDate=date.max,
            EmploymentStatusIndicator=True,
        )
    )
    return sd_employment


def get_mo_employees(gql_client: GraphQLClient) -> List[Employee]:
    """
    Get all MO employees

    Args:
        gql_client: the GraphQL client

    Returns:
        List of CPR numbers
    """

    query = gql(
        """
            query GetEmployees {
                employees {
                    objects {
                        validities {
                            cpr_number
                            uuid
                        }
                    }
                }
            }
        """
    )
    r = gql_client.execute(query)

    employees = []
    for obj in r["employees"]["objects"]:
        validity = one(obj["validities"])
        try:
            employees.append(
                Employee(cpr_no=validity["cpr_number"], uuid=validity["uuid"])
            )
        except ValueError:
            print("Found invalid CPR!")
            print(employee)

    return employees


def terminate_engagement(
    gql_client: GraphQLClient, engagement_uuid: str, termination_date: str
) -> None:
    """
    Terminate a MO engagement.

    Args:
        gql_client: the GraphQL client
        engagement_uuid: UUID of the engagement to terminate
        termination_date: the last day of work for the engagement
    """
    graphql_terminate_engagement = gql(
        """
            mutation TerminateEngagement($input: EngagementTerminateInput!) {
                engagement_terminate(input: $input) {
                    uuid
                }
            }
        """
    )

    gql_client.execute(
        graphql_terminate_engagement,
        variable_values={
            "input": {"uuid": str(engagement_uuid), "to": termination_date}
        },
    )


def get_mo_engagements(
    gql_client: GraphQLClient, employee_uuid: UUID
) -> list[dict[str, Any]]:
    """
    Get MO engagements for a given employee.

    Args:
        gql_client: the GraphQL client
        employee_uuid: UUID of the employee to get the engagements from

    Returns:
        List of dicts where each dict contains user keys, "from date" and
        UUID of the engagements
    """

    query = gql(
        """
            query GetEngagements(
              $uuid: [UUID!]!
              $from_date: DateTime
              $to_date: DateTime
            ) {
              engagements(
                filter: {
                  from_date: $from_date
                  to_date: $to_date
                  employee: { uuids: $uuid }
                }
              ) {
                objects {
                  validities {
                    uuid
                    user_key
                    validity {
                      from
                      to
                    }
                  }
                }
              }
            }
        """
    )

    r = gql_client.execute(
        query,
        variable_values={
            "uuid": str(employee_uuid),
            "from_date": datetime.now().isoformat(),
            "to_date": None,
        },
    )
    engagements = [
        {
            "uuid": last(obj["validities"])["uuid"],
            "user_key": last(obj["validities"])["user_key"],
            "to": datetime.fromisoformat(last(obj["validities"])["validity"]["to"])
            if last(obj["validities"])["validity"]["to"] is not None
            else None,
        }
        for obj in r["engagements"]["objects"]
    ]
    return engagements


def get_last_day_of_work(
    sd_employment_changed: GetEmploymentChangedResponse,
) -> date:
    """
    Get the last day when the SD employment was active.

    Args:
        sd_employment_changed: the SD employments
        cpr: CPR number of the employee
        emp_id: the SD EmploymentIdentifier

    Returns:
        Last active day of work for the SD employment.
    """
    person = only(sd_employment_changed.Person)

    if person is None:
        # Dang - this seems very dangerous, since we terminate the engagement
        # in MO, if the person cannot be found in SD
        return date.today()

    employment = only(person.Employment)
    if employment is None:
        # Dang dang - once again!
        return date.today()

    active_statuses = [
        emp_status
        for emp_status in employment.EmploymentStatus
        if emp_status.EmploymentStatusCode not in ("7", "8", "9", "S")
    ]
    active_statuses.sort(key=lambda status: status.ActivationDate)

    return last(active_statuses).DeactivationDate


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
    default="http://keycloak:8080/auth",
    help="Keycloak auth server URL",
)
@click.option(
    "--client-id",
    "client_id",
    type=click.STRING,
    default="developer",
    help="Keycloak client id",
)
@click.option(
    "--client-secret",
    "client_secret",
    type=click.STRING,
    required=True,
    help="Keycloak client secret for the 'developer' client",
)
@click.option(
    "--mo-base-url",
    "mo_base_url",
    type=click.STRING,
    default="http://mo:5000",
    help="Base URL for calling MO",
)
@click.option(
    "--make-changes-in-mo",
    is_flag=True,
    help="If set, perform changes in MO (make sure you know, what you are doing)!",
)
@click.option(
    "--i-have-read-the-readme",
    "readme",
    is_flag=True,
    help="Set flag to ensure that you have read the readme",
)
@click.option(
    "--show-cpr",
    "show_cpr",
    is_flag=True,
    help="Show CPRs in output",
)
def main(
    username: str,
    password: str,
    institution_identifier: str,
    auth_server: str,
    client_id: str,
    client_secret: str,
    mo_base_url: str,
    make_changes_in_mo: bool,
    readme: bool,
    show_cpr: bool,
) -> None:
    if not readme:
        print("Make sure you have read the README.md before running the script")
        exit(1)

    # Shut up RAClients!
    setup_logging(LogLevel.DEBUG)

    gql_client = get_mo_client(auth_server, client_id, client_secret, mo_base_url, 22)
    employees = get_mo_employees(gql_client)

    print("Terminate engagements")
    for i, employee_ in enumerate(employees):
        if i % 100 == 0:
            print(f"Processed employees: {i}/{len(employees)}")
        engagements = get_mo_engagements(gql_client, employee_.uuid)
        for eng in engagements:
            try:
                UUID(eng["user_key"])
                continue
            except ValueError:
                pass
            sd_employment_changed = get_sd_employment_changed(
                username=username,
                password=password,
                institution_identifier=institution_identifier,
                cpr=employee_.cpr_no,
                employment_identifier=eng["user_key"],
            )

            sd_last_day_of_work = get_last_day_of_work(sd_employment_changed)
            sd_last_day_of_work_str = format_date(sd_last_day_of_work)

            mo_last_day_of_work = (
                eng["to"].date() if eng["to"] is not None else date.max
            )
            mo_last_day_of_work_str = format_date(mo_last_day_of_work)

            if sd_last_day_of_work == mo_last_day_of_work:
                continue
            elif sd_last_day_of_work > mo_last_day_of_work:
                print(
                    employee_.cpr_no if show_cpr else anonymize_cpr(employee_.cpr_no),
                    eng["user_key"],
                    sd_last_day_of_work_str,
                    mo_last_day_of_work_str,
                    "SD validity exceeds MO validity",
                )
                continue

            print(
                employee_.cpr_no if show_cpr else anonymize_cpr(employee_.cpr_no),
                eng["user_key"],
                sd_last_day_of_work_str,
                mo_last_day_of_work_str,
            )
            if not make_changes_in_mo:
                continue
            terminate_engagement(gql_client, eng["uuid"], sd_last_day_of_work_str)


if __name__ == "__main__":
    main()
