from datetime import datetime, date, timedelta
from typing import Any
from uuid import UUID

import click
from gql import gql
from more_itertools import one, last, only
from raclients.graph.client import GraphQLClient
from sdclient.client import SDClient
from sdclient.requests import GetEmploymentRequest
from sdclient.responses import GetEmploymentResponse

from sdlon.date_utils import format_date, parse_datetime, SD_INFINITY
from sdlon.graphql import get_mo_client
from sdlon.log import setup_logging, LogLevel, anonymize_cpr
from sdlon.scripts import print_json
from sdlon.sd_common import EmploymentStatus as SDEmpStatus

# Shut up RAClients!
setup_logging(LogLevel.ERROR)


def get_sd_employments(
    username: str,
    password: str,
    institution_identifier: str,
    cpr: str,
    employment_id: str,
    effective_date: date,
) -> GetEmploymentResponse:
    sd_client = SDClient(username, password)
    sd_employments = sd_client.get_employment(
        GetEmploymentRequest(
            InstitutionIdentifier=institution_identifier,
            PersonCivilRegistrationIdentifier=cpr,
            EmploymentIdentifier=employment_id,
            EffectiveDate=effective_date,
            EmploymentStatusIndicator=True,
        )
    )
    return sd_employments


def get_final_sd_employment_end_date(
        username: str,
        password: str,
        institution_identifier: str,
        cpr: str,
        employment_id: str,
        effective_date: date,
) -> date | None:
    sd_employments = get_sd_employments(
        username,
        password,
        institution_identifier,
        cpr,
        employment_id,
        effective_date,
    )

    emp = one(one(sd_employments.Person).Employment)

    if SDEmpStatus(emp.EmploymentStatus.EmploymentStatusCode) not in SDEmpStatus.employeed():
        return None

    while SDEmpStatus(emp.EmploymentStatus.EmploymentStatusCode) in SDEmpStatus.employeed():
        end_date = emp.EmploymentStatus.DeactivationDate

        if format_date(end_date) == SD_INFINITY:
            return end_date

        next_effective_date = emp.EmploymentStatus.DeactivationDate + timedelta(days=1)
        next_emp = get_sd_employments(
            username,
            password,
            institution_identifier,
            cpr,
            employment_id,
            next_effective_date
        )
        emp = one(one(next_emp.Person).Employment)

    return end_date


def get_mo_leaves(gql_client: GraphQLClient, from_date: datetime) -> list[dict[str, Any]]:
    """
    Get MO leaves. Return something like this:

    [
      {
        "person": [
          {
            "cpr_number": "2805582599"
          }
        ],
        "uuid": "60e433ee-01d9-43e8-b52f-34358d6f9058",
        "validity": {
          "from": "2022-01-01T00:00:00+01:00",
          "to": "2024-01-01T00:00:00+01:00"
        },
        "user_key": "12345"
      }
    ]
    """

    query = gql(
        """
        query GetLeaves($from_date: DateTime) {
          leaves(filter: {from_date: $from_date, to_date: null}) {
            objects {
              objects {
                person {
                  cpr_number
                  uuid
                }
                uuid
                validity {
                  from
                  to
                }
                user_key
              }
            }
          }
        }
        """
    )

    r = gql_client.execute(
        query,
        variable_values={
            "from_date": format_date(from_date)
        }
    )

    leave_objs = r["leaves"]["objects"]
    return [
        one(obj["objects"]) for obj in leave_objs
    ]


def get_mo_engagement(
    gql_client: GraphQLClient, employee_uuid: UUID, user_key: str
) -> dict[str, Any]:
    query = gql(
        """
        query GetEngagement($employee_uuid: [UUID!], $user_key: [String!]) {
          engagements(filter: {
            employees: $employee_uuid,
            user_keys: $user_key,
            from_date: null,
            to_date: null
          }) {
            objects {
              objects {
                user_key
                validity {
                  from
                  to
                }
              }
              uuid
            }
          }
        }
        """
    )

    r = gql_client.execute(
        query,
        variable_values={
            "employee_uuid": str(employee_uuid),
            "user_key": user_key
        }
    )

    return one(r["engagements"]["objects"])


def update_engagement_end_date(
        gql_client: GraphQLClient,
        engagement_uuid: UUID,
        from_date: date,
        to_date: date
) -> None:
    mutation = gql(
        """
        mutation EngagementUpdate(
          $uuid: UUID!,
          $from_date: DateTime!,
          $to_date: DateTime
        ) {
          engagement_update(
            input: {
              uuid: $uuid,
              validity: {
                from: $from_date,
                to: $to_date
              }
            }
          ) {
            uuid
          }
        }
        """
    )

    gql_client.execute(mutation, variable_values={
        "uuid": str(engagement_uuid),
        "from_date": format_date(from_date),
        "to_date": format_date(to_date) if not date == date.max else None
    })


def get_eng_dates(eng: dict[str, Any]) -> tuple[date, date]:
    from_str = eng["validity"]["from"]
    to_str = eng["validity"]["to"]

    from_ = datetime.fromisoformat(from_str).date() if from_str is not None else date.min
    to = datetime.fromisoformat(to_str).date() if to_str is not None else date.max

    return from_, to


def get_latest_eng_dates(engagement: dict[str, Any], sd_final_end_date: date) -> tuple[date, date] | None:
    eng_objs = engagement["objects"]
    # eng_objs.sort(key=lambda obj: datetime.fromisoformat(obj["validity"]["to"]).date())

    # Assuming the eng_objs are always sorted in the response from MO!
    latest_eng = last(eng_objs)
    latest_eng_from, latest_eng_to = get_eng_dates(latest_eng)

    if latest_eng_to < sd_final_end_date:
        return latest_eng_from, latest_eng_to
        # print("-- Update engagement:", engagement["uuid"])
        # print("latest_eng_from:", latest_eng_from)
        # print("latest_eng_to:", latest_eng_to)
        # print("sd_final_end_date", sd_final_end_date)
        # print_json(engagement)
    return None


def cpr_leaves_filter(leaves: list[dict[str, Any]], cpr: str) -> list[dict[str, Any]]:
    return [
        leave for leave in leaves
        if one(leave["person"])["cpr_number"] == cpr
    ]


@click.command()
@click.option(
    "--username",
    envvar="SD_USER",
    required=True,
    help="SD username"
)
@click.option(
    "--password",
    envvar="SD_PASSWORD",
    required=True,
    help="SD password"
)
@click.option(
    "--institution-identifier",
    envvar="SD_INSTITUTION_IDENTIFIER",
    required=True,
    help="SD institution identifier"
)
@click.option(
    "--auth-server",
    default="http://localhost:8090/auth",
    envvar="AUTH_SERVER",
    help="Keycloak auth server URL"
)
@click.option(
    "--client-id",
    default="dipex",
    envvar="CLIENT_ID",
    help="Keycloak client id"
)
@click.option(
    "--client-secret",
    required=True,
    envvar="CLIENT_SECRET",
    help="Keycloak client secret for the DIPEX client"
)
@click.option(
    "--mo-base-url",
    default="http://localhost:5000",
    envvar="MORA_BASE",
    help="Base URL for calling MO"
)
@click.option(
    "--effective-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=date.strftime(datetime.now(), "%Y-%m-%d"),
    help="Fix from this date an forward"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Do not perform any changes in MO"
)
@click.option(
    "--cpr",
    help="Only run script for this CPR"
)
def main(
        username: str,
        password: str,
        institution_identifier: str,
        auth_server: str,
        client_id: str,
        client_secret: str,
        mo_base_url: str,
        effective_date: datetime,
        dry_run: bool,
        cpr: str,
):
    print("Starting script...")

    gql_client = get_mo_client(
        auth_server, client_id, client_secret, mo_base_url, 19
    )

    leaves = get_mo_leaves(gql_client, effective_date)
    if cpr is not None:
        leaves = cpr_leaves_filter(leaves, cpr)
    # print_json(leaves)

    for leave in leaves:
        user_key = leave["user_key"]
        person = one(leave["person"])
        print(f"Processing user_key={user_key} cpr={person['cpr_number']}")

        try:
            engagement = get_mo_engagement(gql_client, UUID(person["uuid"]), user_key)
            # print_json(engagement)
        except ValueError:
            print(f"Could not find engagement with user_key {user_key} for person {person['uuid']}")
            continue

        try:
            sd_final_end_date = get_final_sd_employment_end_date(
                username,
                password,
                institution_identifier,
                person["cpr_number"],
                user_key,
                effective_date.date(),
            )

            latest_eng_dates = get_latest_eng_dates(engagement, sd_final_end_date)
            if latest_eng_dates is not None:
                anonymized_cpr = anonymize_cpr(person["cpr_number"])
                print(
                    "Update engagement",
                    anonymized_cpr,
                    user_key,
                    format_date(datetime.fromisoformat(leave["validity"]["from"]).date() if leave["validity"]["from"] is not None else date.min),
                    format_date(datetime.fromisoformat(leave["validity"]["to"]).date() if leave["validity"]["to"] is not None else date.max),
                    format_date(sd_final_end_date),
                    format_date(latest_eng_dates[0]),
                    format_date(latest_eng_dates[1]),
                )
                if not dry_run:
                    update_engagement_end_date(
                        gql_client,
                        engagement_uuid=UUID(engagement["uuid"]),
                        from_date=latest_eng_dates[0],
                        to_date=sd_final_end_date
                    )
        except ValueError:
            print(f"Could not find SD end date for {user_key}")


if __name__ == "__main__":
    main()
