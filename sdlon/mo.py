import base64
from datetime import datetime
from uuid import UUID

from gql import gql

from sdlon.graphql import get_mo_client


class MO:
    def __init__(
        self,
        auth_server: str,
        client_id: str,
        client_secret: str,
        mo_base_url: str,
        timeout: int = 600,
    ):
        self.client = get_mo_client(
            auth_server=auth_server,
            client_id=client_id,
            client_secret=client_secret,
            mo_base_url=mo_base_url,
            gql_version=21,
            timeout=timeout,
        )

    def get_engagements(
        self,
        from_date: datetime | None,
        to_date: datetime | None,
        include_org_unit: bool = False,
    ):
        """
        Get all current and future engagements
        """

        # I know - this is ugly...
        ou_part = (
            """
                    org_unit {
                      uuid
                      user_key
                      name
                      managers {
                        employee {
                          uuid
                          name
                        }
                      }
                    }
        """
            if include_org_unit
            else ""
        )

        query = gql(
            """
            query GetEngagements(
              $from_date: DateTime,
              $to_date: DateTime,
              $cursor: Cursor,
              $limit: int!
            ) {
              engagements(
                filter: {from_date: $from_date, to_date: $to_date}
                cursor: $cursor
                limit: $limit
              ) {
                objects {
                  validities {
                    person {
                      cpr_number
                      uuid
                    }
            """
            + ou_part
            + """
                    validity {
                      from
                      to
                    }
                    user_key
                  }
                  uuid
                }
                page_info {
                  next_cursor
                }
              }
            }
            """
        )

        def execute(cursor: str | None, objects: list[dict]) -> str:
            response = self.client.execute(
                query,
                variable_values={
                    "limit": "100",
                    "cursor": cursor,
                    "from_date": from_date.isoformat()
                    if from_date is not None
                    else None,
                    "to_date": to_date.isoformat() if to_date is not None else None,
                },
            )
            next_cursor = response["engagements"]["page_info"]["next_cursor"]
            objects.extend(response["engagements"]["objects"])
            return next_cursor

        objects = []
        next_cursor = execute(None, objects)
        while next_cursor:
            print(base64.b64decode(next_cursor.split(":")[1]))
            next_cursor = execute(next_cursor, objects)

        return objects

    def terminate_engagement(
        self,
        eng_uuid: UUID,
        to_date: datetime,
    ) -> None:
        mutation = gql(
            """
            mutation TerminateEngagement(
              $uuid: UUID!,
              $to: DateTime!
            ) {
              engagement_terminate(
                input: {to: $to, uuid: $uuid}
              ) {
                uuid
              }
            }
            """
        )

        self.client.execute(
            mutation, {"uuid": str(eng_uuid), "to": to_date.date().isoformat()}
        )

    def update_engagement(
        self,
        eng_uuid: UUID,
        from_date: datetime,
        to_date: datetime | None,
        org_unit: UUID,
    ) -> None:
        mutation = gql(
            """
            mutation UpdateEngagement(
              $uuid: UUID!,
              $from: DateTime!,
              $to: DateTime,
              $org_unit: UUID!
            ) {
              engagement_update(
                input: {
                  uuid: $uuid,
                  validity: {
                    from: $from,
                    to: $to
                  },
                  org_unit: $org_unit
                }
              ) {
                uuid
              }
            }
            """
        )

        self.client.execute(
            mutation,
            {
                "uuid": str(eng_uuid),
                "from": from_date.isoformat(),
                "to": to_date.isoformat() if to_date is not None else None,
                "org_unit": str(org_unit),
            },
        )
