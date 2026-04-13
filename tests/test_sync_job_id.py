from unittest import TestCase

from sdlon.config import Settings
from sdlon.graphql import get_mo_client
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
        mo_graphql_client = get_mo_client(
            settings.job_settings.auth_realm,
            settings.job_settings.client_id,
            settings.job_settings.client_secret,  # type: ignore
            settings.mora_base,
            29,
        )
        assert isinstance(settings.sd_institution_identifier, str)
        self.job_id_sync = JobIdSyncTest(
            settings, settings.sd_institution_identifier, mo_graphql_client
        )

    def test_create(self):
        self.assertTrue(self.job_id_sync.update_job_functions)
