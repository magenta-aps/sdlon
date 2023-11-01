from datetime import datetime
from uuid import UUID

import click
from gql import gql
from raclients.graph.client import GraphQLClient

from sdlon.date_utils import format_date
from sdlon.graphql import get_mo_client
from sdlon.log import setup_logging, LogLevel
from sdlon.scripts import print_json
from sdlon.scripts.mo import terminate_engagement

# Shut up RAClients!
setup_logging(LogLevel.ERROR)


def create_engagement(
        gql_client: GraphQLClient,
        person: UUID,
        org_unit: UUID,
        engagement_type: UUID,
        user_key: str,
        job_function: UUID,
        from_date: datetime,
        to_date: datetime
) -> UUID:
    mutation = gql(
        """
        mutation CreateEngagement(
          $org_unit: UUID!,
          $person: UUID,
          $engagement_type: UUID!,
          $user_key: String,
          $job_function: UUID!,
          $from_date: DateTime!,
          $to_date: DateTime
        ) {
          engagement_create(
            input: {
              validity: {
                from: $from_date,
                to: $to_date
              },
              user_key: $user_key,
              org_unit: $org_unit,
              person: $person,
              engagement_type: $engagement_type,
              job_function: $job_function
            }
          ) {
            uuid
          }
        }
        """
    )

    r = gql_client.execute(mutation, variable_values={
        "person": str(person),
        "org_unit": str(org_unit),
        "engagement_type": str(engagement_type),
        "user_key": user_key,
        "job_function": str(job_function),
        "from_date": format_date(from_date),
        "to_date": format_date(to_date)
    })

    return UUID(r["engagement_create"]["uuid"])


def create_leave(
        gql_client: GraphQLClient,
        person: UUID,
        user_key: str,
        engagement: UUID,
        leave_type: UUID,
        from_date: datetime,
        to_date: datetime
) -> dict:
    mutation = gql(
        """
        mutation CreateLeave(
            $person: UUID!,
            $user_key: String,
            $engagement: UUID!,
            $leave_type: UUID!,
            $from_date: DateTime!,
            $to_date: DateTime    
          ) {
          leave_create(
            input: {
              person: $person,
              user_key: $user_key,
              engagement: $engagement,
              leave_type: $leave_type,
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

    r = gql_client.execute(mutation, variable_values={
        "person": str(person),
        "user_key": user_key,
        "engagement": str(engagement),
        "leave_type": str(leave_type),
        "from_date": format_date(from_date),
        "to_date": format_date(to_date)
    })

    return r


@click.command()
@click.option(
    "--auth-server",
    default="http://localhost:8090/auth",
    help="Keycloak auth server URL"
)
@click.option(
    "--client-id",
    default="dipex",
    help="Keycloak client id"
)
@click.option(
    "--client-secret",
    required=True,
    help="Keycloak client secret for the DIPEX client"
)
@click.option(
    "--mo-base-url",
    default="http://localhost:5000",
    help="Base URL for calling MO"
)
def main(
        auth_server: str,
        client_id: str,
        client_secret: str,
        mo_base_url: str,
):
    gql_client = get_mo_client(
        auth_server, client_id, client_secret, mo_base_url, 19
    )

    person = UUID("eff3fca2-645c-4613-90ad-5fb47db47bc7")  # Lykke Skytte Hansen
    user_key="12345"

    engagement_uuid = create_engagement(
        gql_client,
        person=person,
        org_unit=UUID("f06ee470-9f17-566f-acbe-e938112d46d9"),  # Kolding Kommune
        engagement_type=UUID("8acc5743-044b-4c82-9bb9-4e572d82b524"),  # Ansat
        user_key=user_key,
        job_function=UUID("cf84f415-a6bd-4b4d-9b06-91ea392a8543"),  # Bogopsætter
        from_date=datetime(2020, 1, 1),
        to_date=datetime(2023, 9, 1)
    )
    print("Engagement created", engagement_uuid)

    leave = create_leave(
        gql_client,
        person,
        user_key,
        engagement_uuid,
        UUID("55bade7f-8efc-04fc-90b0-0b6e4de69260"),
        datetime(2022, 1, 1),
        datetime(2024, 1, 1),
    )
    print(leave)

    # terminate_engagement(gql_client, str(engagement_uuid), "2023-01-01")


if __name__ == "__main__":
    main()
