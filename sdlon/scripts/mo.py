from gql import gql
from raclients.graph.client import GraphQLClient


def terminate_engagement(
        gql_client: GraphQLClient,
        engagement_uuid: str,
        termination_date: str
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

    gql_client.execute(graphql_terminate_engagement, variable_values={
        "input": {
            "uuid": str(engagement_uuid),
            "to": termination_date
        }
    })
