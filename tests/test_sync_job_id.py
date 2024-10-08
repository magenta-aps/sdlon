from unittest import TestCase

from sdlon.config import Settings
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
        self.job_id_sync = JobIdSyncTest(settings, settings.sd_institution_identifier)

    def test_create(self):
        self.assertTrue(self.job_id_sync.update_job_functions)
