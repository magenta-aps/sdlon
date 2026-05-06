import uuid

from gql.gql import gql
from more_itertools import one
from os2mo_helpers.mora_helpers import MoraHelper
from raclients.graph.client import GraphQLClient
from structlog.stdlib import get_logger

from .config import Settings
from .models import JobFunction
from .sd_common import sd_lookup

logger = get_logger()


class JobIdSync:
    def __init__(
        self, settings: Settings, current_inst_id: str, mo_graphql_client: GraphQLClient
    ):
        logger.info("Start sync")
        self.settings = settings
        self.current_inst_id = current_inst_id
        self.mo_graphql_client = mo_graphql_client

        sd_job_function = self.settings.sd_job_function
        if sd_job_function == JobFunction.job_position_identifier:
            logger.info("Read settings. Update job_functions and engagment types")
            self.update_job_functions = True
        else:
            logger.info("Read settings. Do not update job_functions")
            self.update_job_functions = False

        self._read_classes()

    def _read_classes(self):
        """Read engagement_types and job_function types from MO."""
        mora_base = self.settings.mora_base
        helper = MoraHelper(hostname=mora_base, use_cache=False)

        self.engagement_types = helper.read_classes_in_facet("engagement_type")
        if self.update_job_functions:
            self.job_function_types = helper.read_classes_in_facet(
                "engagement_job_function"
            )

    def _find_engagement_type(self, job_pos_id):
        """
        Find a Klasse in facet engagement_type corresponding to job_pos_id in LoRa.
        The search is performed both by direct search as well as with prefixed
        string engagement_type (which is used in the municipalities who also use
        the job_pos_ids as job_functions).
        """
        logger.info("Search MO for engagment_type {}".format(job_pos_id))
        found_type = None
        user_keys = [str(job_pos_id), "engagement_type" + str(job_pos_id)]
        for engagement_type in self.engagement_types[0]:
            if engagement_type["user_key"] in user_keys:
                found_type = engagement_type
        logger.info("Found {}".format(found_type))
        return found_type

    def _find_job_function_type(self, job_pos_id):
        """
        Find the Klasse corresponding to job_pos_id in LoRa.
        """
        found_type = None
        if not self.update_job_functions:
            logger.info("Job functons not enabled in settings")
            return None

        logger.info("Search MO for job_function_type {}".format(job_pos_id))
        # Currently we do not use a prefix anywhere, list has only one element
        user_keys = [str(job_pos_id)]
        for job_function_type in self.job_function_types[0]:
            if job_function_type["user_key"] in user_keys:
                found_type = job_function_type
        logger.info("Found {}".format(found_type))
        return found_type

    def _edit_klasse_title(self, uuid: str, title: str) -> None:
        """
        Change the title of an existing MO class.
        """

        logger.info("Edit {} title to {}".format(uuid, title), uuid=uuid, title=title)

        # since it's not currently possible to update individual fields on the
        # graphql API, we first need to fetch all the fields the class needs
        query = gql(
            """
            query GetClass($uuid: UUID!) {
                classes(filter: {uuids: [$uuid]}) {
                    objects {
                        current {
                            user_key
                            facet_response {
                                uuid
                            }
                        }
                    }
                }
            }
            """
        )
        query_response = self.mo_graphql_client.execute(
            query, variable_values={"uuid": uuid}
        )
        logger.info("GetClass query responded", response=query_response)
        klass = one(query_response["classes"]["objects"])
        mutation = gql(
            """
            mutation UpdateClass($input: UpdateClassInput!) {
                class_update(input: $input) {
                    uuid
                }
            }
            """
        )
        mutation_response = self.mo_graphql_client.execute(
            mutation,
            variable_values={
                "input": {
                    "uuid": uuid,
                    "name": title,
                    "user_key": klass["current"]["user_key"],
                    "facet_uuid": klass["current"]["facet_response"]["uuid"],
                    "validity": {"from": "1930-01-01"},
                    "scope": "TEXT",
                }
            },
        )
        logger.info("UpdateClass mutation responded", response=mutation_response)
        assert mutation_response["class_update"]["uuid"] == uuid

    def _get_job_pos_id_from_sd(self, job_pos_id):
        """
        Return the textual value of a Job Position Identifier from SD.
        """
        logger.info("Search SD for {}".format(job_pos_id))
        params = {
            "JobPositionIdentifier": job_pos_id,
        }
        request_uuid = uuid.uuid4()
        logger.info("_get_job_pos_id_from_sd", request_uuid=request_uuid)
        try:
            job_pos_response = sd_lookup(
                "GetProfession20080201",
                settings=self.settings,
                params=params,
                request_uuid=request_uuid,
                dry_run=True,
                institution_identifier=self.current_inst_id,
            )
        except Exception:  # TODO: Be specific here
            logger.info("This job_position could not be found in SD")
            return None
        job_pos = None
        while "Profession" in job_pos_response:
            job_pos = job_pos_response["Profession"]["JobPositionName"]
            job_pos_response = job_pos_response["Profession"]
        logger.info("Found {}".format(job_pos_id))
        return job_pos

    def _sync_engagement_type_from_sd(self, job_pos_id, sd_job_pos_text):
        mo_eng_type = self._find_engagement_type(job_pos_id)
        if mo_eng_type is None:
            logger.info("Engagement type {} not found i MO".format(job_pos_id))
            return False

        self._edit_klasse_title(mo_eng_type["uuid"], sd_job_pos_text)
        logger.info("Updated engagement type: {}".format(job_pos_id))
        return True

    def _sync_job_function_from_sd(self, job_pos_id, sd_job_pos_text):
        mo_job_function_type = self._find_job_function_type(job_pos_id)
        if mo_job_function_type is None:
            logger.info("job function type {} not found i MO".format(job_pos_id))
            return False

        self._edit_klasse_title(mo_job_function_type["uuid"], sd_job_pos_text)
        logger.info("Updated job function type type: {}".format(job_pos_id))
        return True

    def sync_from_sd(self, job_pos_id, refresh=False):
        """
        Sync the titel of LoRa engagement type to the value current
        registred at SD.
        """
        # If asked to refresh, reread the classes from MO. This may be necessary if
        # new classes have been added since the creation of this JobIdSync object.
        if refresh:
            self._read_classes()

        logger.info("Sync {} to value found in SD".format(job_pos_id))
        return_status = [None, None]

        sd_job_pos_text = self._get_job_pos_id_from_sd(job_pos_id)
        if sd_job_pos_text is None:
            logger.info("Job position {} not found i SD".format(job_pos_id))
            return return_status

        return_status[0] = self._sync_engagement_type_from_sd(
            job_pos_id, sd_job_pos_text
        )
        # Only run this part, if we are actually using
        if self.update_job_functions:
            return_status[1] = self._sync_job_function_from_sd(
                job_pos_id, sd_job_pos_text
            )

        logger.info("Return status: {}".format(return_status))
        return return_status

    def sync_all_from_sd(self):
        logger.info("Sync all classes")
        for eng_type in self.engagement_types[0]:
            user_key = eng_type["user_key"]
            if user_key.startswith("engagement_type"):
                user_key = user_key[15:]
            print("Sync from SD: {}".format(user_key))
            self.sync_from_sd(user_key)

        if self.update_job_functions:
            for job_function in self.job_function_types[0]:
                user_key = job_function["user_key"]
                print("Sync from SD: {}".format(user_key))
                self.sync_from_sd(user_key)
        logger.info("Full sync completed")

    def sync_manually(self, job_pos_id, title):
        """
        Manually update the titel of an engagement type.
        """
        logger.info("Sync {} to {}".format(job_pos_id, title))
        return_status = [None, None]

        mo_type = self._find_engagement_type(job_pos_id)
        if mo_type is None:
            return_status[0] = False
            logger.info("Job position not found i MO")
        else:
            return_status[0] = True
            self._edit_klasse_titel(mo_type["uuid"], title)

        if self.update_job_functions:
            mo_job_function_type = self._find_job_function_type(job_pos_id)
            if mo_job_function_type is None:
                return_status[1] = False
                logger.info("job function type {} not found i MO".format(job_pos_id))
            else:
                return_status[1] = True
                self._edit_klasse_title(mo_job_function_type["uuid"], title)
                logger.info("Updated job function type type: {}".format(job_pos_id))

        return "Job position updated"
