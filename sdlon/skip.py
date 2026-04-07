from datetime import datetime
from typing import Any
from typing import OrderedDict

from structlog.stdlib import get_logger

from .config import Settings

logger = get_logger()


def cpr_env_filter(settings: Settings, entity: OrderedDict[str, Any]) -> bool:
    cpr = entity["PersonCivilRegistrationIdentifier"]

    if settings.sd_exclude_cprs_mode:
        # The CPRs in the sd_cprs should be excluded from further processing
        # and all other CPRs should be processed
        process_cpr = cpr not in settings.sd_cprs
    else:
        # In this case "exclude mode" is False, i.e. "include mode" is True
        # which means that the cprs in sd_cprs are the ONLY ones that should
        # be processed further
        process_cpr = cpr in settings.sd_cprs

    if not process_cpr and settings.sd_exclude_cprs_mode:
        logger.warning(f"*** SKIPPING employee with cpr={cpr[:6]} ***")

    return process_cpr


def is_valid_cpr(entity) -> bool:
    cpr = entity["PersonCivilRegistrationIdentifier"]

    # CPR check code stolen from the MO code (and modified a bit)
    if len(cpr) > 10:
        logger.warn("Skipping fictional user", cpr=cpr)
        return False

    if cpr[-4:] == "0000":
        logger.warn("Skipping fictional user", cpr=cpr)
        return False

    if isinstance(cpr, str):
        try:
            cpr = int(cpr)
        except ValueError:
            logger.warn("Skipping fictional user", cpr=cpr)
            return False

    rest, code = divmod(cpr, 10000)
    rest, year = divmod(rest, 100)
    rest, month = divmod(rest, 100)
    rest, day = divmod(rest, 100)

    if rest:
        logger.warn("Skipping fictional user", cpr=cpr)
        return False

    # see https://da.wikipedia.org/wiki/CPR-nummer :(
    if code < 4000:
        century = 1900
    elif code < 5000:
        century = 2000 if year <= 36 else 1900
    elif code < 9000:
        century = 2000 if year <= 57 else 1800
    else:
        century = 2000 if year <= 36 else 1900

    try:
        datetime(century + year, month, day)
        return True
    except ValueError:
        logger.warn("Skipping fictional user", cpr=cpr)
        return False


def skip_job_position_id(
    profession: OrderedDict[str, Any], job_pos_ids_to_skip: list[str]
) -> bool:
    """
    Check if SD JobPositionIdentifier is in the list to skip,
    i.e. the list provided via the environment variable
    SD_SKIP_EMPLOYMENT_TYPES

    Args:
        profession: a "Profession" in the list of professions in the
          SD employment.
        job_pos_ids_to_skip: list of SD JobPositionIdentifiers to skip

    Returns:
        True if the SD profession should be skipped and false otherwise.
    """

    job_pos_id = profession.get("JobPositionIdentifier")
    if job_pos_id in job_pos_ids_to_skip:
        return True

    return False
