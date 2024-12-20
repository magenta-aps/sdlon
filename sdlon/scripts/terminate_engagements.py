# (this script is copied from fix_status8.py and modified)
# Find all passive employments in SD and ensure that the corresponding
# engagements in MO are terminated accordingly. The script will:
# 1) Get all status 8 employments from SD
# 2) Iterate over these and terminate the corresponding active engagements in MO
import pathlib
import pickle
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import List
from uuid import UUID

import click
from gql import gql
from more_itertools import exactly_n
from more_itertools import last
from more_itertools import one
from raclients.graph.client import GraphQLClient
from ramodels.mo import employee
from ramodels.mo.employee import Employee
from sdclient.client import SDClient
from sdclient.requests import GetEmploymentRequest
from sdclient.responses import GetEmploymentResponse
from sdclient.responses import Person

from sdlon.date_utils import format_date
from sdlon.graphql import get_mo_client
from sdlon.log import anonymize_cpr as anonymize_cpr_no
from sdlon.log import LogLevel
from sdlon.log import setup_logging


def get_sd_employments(
    username: str, password: str, institution_identifier: str
) -> GetEmploymentResponse:
    """
    Get all passive employments from SD (the query params are very
    specific for what is needed here).

    Args:
        username: the username for the SD API
        password: the password for the SD API
        institution_identifier: the SD institution identifier

    Returns:
        The SD employments
    """

    sd_client = SDClient(username, password)
    sd_employments = sd_client.get_employment(
        GetEmploymentRequest(
            InstitutionIdentifier=institution_identifier,
            EffectiveDate=datetime.now().date(),
            StatusActiveIndicator=False,
            StatusPassiveIndicator=True,
            EmploymentStatusIndicator=True,
        )
    )
    return sd_employments


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


def has_sd_status8(
    sd_employments: GetEmploymentResponse, cpr: str, employment_identifier: str
) -> bool:
    """
    Return True if the MO employee with the given cpr number and
    employment_identifier is in sd_employments

    Args:
        sd_employments: the passive SD employments
        cpr: the CPR number of the employee
        employment_identifier: the SD employment identifier

    Returns:
        True if the combination of CPR and employment identifier has status 8
        in SD and False otherwise
    """

    def has_cpr_and_employment_identifier(person: Person) -> bool:
        cpr_match = cpr == person.PersonCivilRegistrationIdentifier
        employment_identifier_match = exactly_n(
            person.Employment,
            1,
            lambda emp: emp.EmploymentIdentifier == employment_identifier,
        )
        return cpr_match and employment_identifier_match

    return exactly_n(sd_employments.Person, 1, has_cpr_and_employment_identifier)


def get_last_day_of_work(
    sd_employments: GetEmploymentResponse, cpr: str, emp_id: str
) -> date:
    """
    Get the last day when the SD employment was active.

    Args:
        sd_employments: the SD employments
        cpr: CPR number of the employee
        emp_id: the SD EmploymentIdentifier

    Returns:
        Last active day of work for the SD employment.
    """
    sd_person = one(
        person
        for person in sd_employments.Person
        if person.PersonCivilRegistrationIdentifier == cpr
    )
    employment = one(
        emp for emp in sd_person.Employment if emp.EmploymentIdentifier == emp_id
    )

    # SD ActivationDate, i.e. the first day when the employment is no longer active
    activation_date = employment.EmploymentStatus.ActivationDate

    # We need the day before the above date, i.e. the last day of active work
    return activation_date - timedelta(days=1)


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
    help="Keycloak client secret for the DIPEX client",
)
@click.option(
    "--mo-base-url",
    "mo_base_url",
    type=click.STRING,
    default="http://mo:5000",
    help="Base URL for calling MO",
)
@click.option(
    "--use-pickle",
    "use_pickle",
    is_flag=True,
    help="Store SD response locally with pickle and use pickled response "
    "in later runs (useful to avoid unnecessary load on SD during "
    "development)",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, help="Do not perform any changes in MO"
)
@click.option(
    "--i-have-read-the-readme",
    "readme",
    is_flag=True,
    help="Set flag to ensure that you have read the readme",
)
@click.option(
    "--anonymize-cpr",
    "anonymize_cpr",
    is_flag=True,
    help="Anonymize CPRs in output",
)
def main(
    username: str,
    password: str,
    institution_identifier: str,
    auth_server: str,
    client_id: str,
    client_secret: str,
    mo_base_url: str,
    use_pickle: bool,
    dry_run: bool,
    readme: bool,
    anonymize_cpr: bool,
):
    if not readme:
        print("Make sure you have read the README.md before running the script")
        exit(0)

    # Shut up RAClients!
    setup_logging(LogLevel.DEBUG)

    # Get the SD status employments
    if use_pickle:
        pickle_file = "/tmp/sd_employments.bin"
        if not pathlib.Path(pickle_file).is_file():
            sd_employments = get_sd_employments(
                username, password, institution_identifier
            )
            with open(pickle_file, "bw") as fp:
                pickle.dump(sd_employments, fp)
        with open(pickle_file, "br") as fp:
            sd_employments = pickle.load(fp)
    else:
        sd_employments = get_sd_employments(username, password, institution_identifier)

    print("Number of SD employments:", len(sd_employments.Person))

    gql_client = get_mo_client(auth_server, client_id, client_secret, mo_base_url, 22)
    employees = get_mo_employees(gql_client)

    print("Terminate engagements")
    for employee_ in employees:
        engagements = get_mo_engagements(gql_client, employee_.uuid)
        for eng in engagements:
            terminate = has_sd_status8(
                sd_employments, employee_.cpr_no, eng["user_key"]
            )
            if terminate:
                last_day_of_work = get_last_day_of_work(
                    sd_employments, employee_.cpr_no, eng["user_key"]
                )
                last_day_of_work_str = format_date(last_day_of_work)
                print(
                    anonymize_cpr_no(employee_.cpr_no)
                    if anonymize_cpr
                    else employee_.cpr_no,
                    eng["user_key"],
                    last_day_of_work_str,
                    format_date(eng["to"].date()) if eng["to"] is not None else None,
                    terminate,
                )
                if not dry_run:
                    terminate_engagement(gql_client, eng["uuid"], last_day_of_work_str)


if __name__ == "__main__":
    main()
