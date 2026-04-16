from unittest import TestCase
from unittest import mock
from unittest.mock import MagicMock
from uuid import uuid4

from sdlon.config import Settings
from sdlon.graphql import GraphQLClient
from sdlon.sync_job_id import JobIdSync


class JobIdSyncTest(JobIdSync):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _read_classes(self):
        self.engagement_types = []
        self.job_function_types = []


class Test_sync_job_id(TestCase):
    def setUp(self):
        settings = Settings(
            municipality_name="name",
            municipality_code=100,
            mora_base="http://dummy.url",
            sd_job_function="JobPositionIdentifier",
            sd_institution_identifier="XY",
            sd_monthly_hourly_divide=9000,
            sd_password="secret",
            sd_user="user",
            sd_global_from_date="2022-01-09",
            app_dbpassword="secret",
        )
        assert isinstance(settings.sd_institution_identifier, str)
        self.job_id_sync = JobIdSyncTest(
            settings, settings.sd_institution_identifier, MagicMock()
        )

    def test_create(self):
        self.assertTrue(self.job_id_sync.update_job_functions)

    def test__edit_klasse_title(self):
        # Arrange
        class_uuid = str(uuid4())
        facet_uuid = str(uuid4())
        mock_gql_client = MagicMock(spec=GraphQLClient)
        execute_side_effect = [
            {
                "classes": {
                    "objects": [
                        {
                            "current": {
                                "user_key": "user_key",
                                "facet_response": {"uuid": facet_uuid},
                            }
                        }
                    ]
                }
            },
            {"class_update": {"uuid": class_uuid}},
        ]
        mock_execute = MagicMock(side_effect=execute_side_effect)
        mock_gql_client.execute = mock_execute
        self.job_id_sync.mo_graphql_client = mock_gql_client

        # Act
        self.job_id_sync._edit_klasse_title(class_uuid, "title")

        # Assert
        mock_execute.assert_has_calls(
            [
                mock.call(mock.ANY, variable_values={"uuid": class_uuid}),
                mock.call(
                    mock.ANY,
                    variable_values={
                        "input": {
                            "uuid": class_uuid,
                            "name": "title",
                            "user_key": "user_key",
                            "facet_uuid": facet_uuid,
                            "validity": {"from": "1930-01-01"},
                            "scope": "TEXT",
                        }
                    },
                ),
            ]
        )
