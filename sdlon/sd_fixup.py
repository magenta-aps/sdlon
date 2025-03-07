import datetime
from datetime import date
from functools import partial
from operator import itemgetter
from typing import List
from typing import Optional
from typing import Tuple
from uuid import UUID
from uuid import uuid4

import click
import httpx
from gql import gql
from more_itertools import consume
from more_itertools import flatten
from more_itertools import one
from more_itertools import only
from more_itertools import side_effect
from more_itertools import unzip
from os2mo_helpers.mora_helpers import MoraHelper
from ra_utils.apply import apply
from ra_utils.load_settings import load_setting
from raclients.graph.client import GraphQLClient
from raclients.graph.client import SyncClientSession
from structlog.stdlib import get_logger
from tqdm import tqdm

from . import sd_payloads
from .config import get_settings
from .config import Settings
from .date_utils import sd_to_mo_date
from .sd_changed_at import ChangeAtSD
from .sd_common import EmploymentStatus
from .sd_common import mora_assert
from .sd_common import sd_lookup


logger = get_logger()


def fetch_user_employments(settings: Settings, cpr: str) -> List:
    # Notice, this will not get future engagements
    params = {
        "PersonCivilRegistrationIdentifier": cpr,
        "StatusActiveIndicator": "true",
        "StatusPassiveIndicator": "true",
        "DepartmentIndicator": "true",
        "EmploymentStatusIndicator": "true",
        "ProfessionIndicator": "true",
        "WorkingTimeIndicator": "true",
        "UUIDIndicator": "true",
        "SalaryAgreementIndicator": "false",
        "SalaryCodeGroupIndicator": "false",
        "EffectiveDate": date.today().strftime("%d.%m.%Y"),
    }
    request_uuid = uuid4()
    logger.info("fetch_user_employments", request_uuid=request_uuid)
    assert isinstance(settings.sd_institution_identifier, str)
    sd_employments_response = sd_lookup(
        "GetEmployment20111201",
        settings=settings,
        params=params,
        request_uuid=request_uuid,
        dry_run=True,
    )
    if "Person" not in sd_employments_response:
        return []

    employments = sd_employments_response["Person"]["Employment"]
    if not isinstance(employments, list):
        employments = [employments]

    return employments


def get_orgfunc_from_vilkaarligrel(
    class_uuid: str, mox_base: str = "http://localhost:5000/lora"
) -> dict:
    url = f"{mox_base}/organisation/organisationfunktion"
    params = {"vilkaarligrel": class_uuid, "list": "true", "virkningfra": "-infinity"}
    r = httpx.get(url, params=params)
    r.raise_for_status()
    return only(r.json()["results"], default={})


def get_user_from_org_func(org_func: dict) -> Optional[str]:
    registrations = one(org_func["registreringer"])
    user = one(registrations["relationer"]["tilknyttedebrugere"])
    return user["uuid"]


def filter_missing_data(leave: dict) -> bool:
    return not one(leave["registreringer"])["relationer"].get("tilknyttedefunktioner")


def delete_orgfunc(uuid: str, mox_base: str = "http://localhost:5000/lora") -> None:
    r = httpx.delete(f"{mox_base}/organisation/organisationfunktion/{uuid}")
    r.raise_for_status()


def fixup(ctx, mo_employees):
    def fetch_mo_engagements(mo_employee) -> dict:
        mo_uuid = mo_employee["uuid"]
        mo_engagements = mora_helper.read_user_engagement(user=mo_uuid, read_all=True)
        userkeys = map(itemgetter("user_key"), mo_engagements)
        mo_dict = dict(zip(userkeys, mo_engagements))
        return mo_dict

    def fetch_sd_employments(settings, mo_employee):
        mo_cpr = mo_employee["cpr_no"]
        sd_employments = fetch_user_employments(settings, mo_cpr)
        sd_ids = map(itemgetter("EmploymentIdentifier"), sd_employments)
        sd_dict = dict(zip(sd_ids, sd_employments))
        return sd_dict

    def fetch_pairs(settings, mo_employee):
        try:
            mo_dict = fetch_mo_engagements(mo_employee)
            if not mo_dict:
                return None
            sd_dict = fetch_sd_employments(settings, mo_employee)
            return mo_dict, sd_dict
        except Exception as exp:
            print(mo_employee)
            print(exp)
            return None

    def process_tuples(mo_dict, sd_dict):
        # Find intersection
        common_keys = mo_dict.keys() & sd_dict.keys()
        for key in common_keys:
            yield (key, mo_dict[key], sd_dict[key])

    def generate_payload(work_tuple):
        key, mo_engagement, sd_employment = work_tuple
        print("Fixing", key)
        data = {
            "validity": {
                "from": mo_engagement["validity"]["from"],
                "to": sd_to_mo_date(
                    sd_employment["EmploymentDepartment"]["DeactivationDate"]
                ),
            },
        }
        payload = sd_payloads.engagement(data, mo_engagement)
        return payload

    mora_helper = ctx["mora_helper"]
    settings: Settings = ctx["settings"]

    if ctx["progress"]:
        mo_employees = tqdm(mo_employees, unit="Employee")

    # Dict pair is a list of (dict, dict) tuples
    # First dict is a mapping from employment_id to mo_engagement
    # Second dict is a mapping from employment_id to sd_engagement
    dict_pairs = [
        dicts
        for mo_employee in mo_employees
        if (dicts := fetch_pairs(settings, mo_employee)) is not None
    ]

    # Convert dict_pairs into an iterator of three tuples:
    # (key, mo_engagement, sd_employment)
    # 'key' is the shared employment_id
    work_tuples = flatten(map(process_tuples, *unzip(dict_pairs)))
    # At this point, we have a tuple of items which need to be updated / fixed

    # Convert all the remaining tuples to MO payloads
    payloads = map(generate_payload, work_tuples)

    if ctx["dry_run"]:
        print("Dry-run. Would send the following payloads:")
        for p in payloads:
            print(p)
        return

    for payload in payloads:
        response = mora_helper._mo_post("details/edit", payload)
        mora_assert(response)


def read_associations(session: SyncClientSession, org_unit_uuids: list[UUID]):
    """Query every association to the provided org_units"""
    query = gql(
        """
        query AssociationsQuery ($org_units: [UUID!]) {
            associations(filter: {org_units: $org_units}) {
                objects {
                    validities {
                        uuid
                        association_type_uuid
                        validity {
                            from
                        }
                    }
                }
            }
        }
    """
    )
    r = session.execute(
        query, variable_values={"org_units": [str(u) for u in org_unit_uuids]}
    )
    return [one(a["validities"]) for a in r["associations"]["objects"]]


def fix_association_types(
    session: SyncClientSession,
    association_uuid: UUID,
    from_date: str,
    correct_association_type_uuid: UUID,
):
    """Update given associations with the given association type"""
    query = gql(
        """
    mutation UpdateAssociation($uuid: UUID!, $from: DateTime!, $association_type: UUID!) {
            association_update(
            input: {uuid: $uuid, validity: {from: $from}, association_type: $association_type}
            ) {
                uuid
            }
        }
    """  # noqa
    )
    session.execute(
        query,
        variable_values={
            "uuid": str(association_uuid),
            "from": from_date,
            "association_type": str(correct_association_type_uuid),
        },
    )


@click.group()
@click.option(
    "--mora-base",
    default="http://localhost:5000",
    help="URL for MO.",
    envvar="MORA_BASE",
)
@click.option("--json/--no-json", default=False, help="Output as JSON.")
@click.option("--progress/--no-progress", default=False, help="Print progress.")
@click.option("--fixup-status-0", default=False, help="Attempt to fix status-0 issues.")
@click.option(
    "--dry-run/--no-dry-run", default=False, help="Dry-run making no actual changes."
)
@click.pass_context
def cli(ctx, mora_base, **kwargs):
    """Tool to fixup MO entries according to SD data.

    This tool should never be needed, as it indicates issues in the main code.
    It is however needed due to the quality of the main code.
    """
    # ensure that ctx.obj exists and is a dict, no matter how it is called.
    ctx.ensure_object(dict)
    ctx.obj = dict(kwargs)
    ctx.obj["mora_base"] = mora_base
    ctx.obj["mora_helper"] = MoraHelper(hostname=mora_base, use_cache=False)
    ctx.obj["settings"] = get_settings()


@cli.command()
@click.option(
    "--uuid", type=click.UUID, help="UUID of the user to check.", required=True
)
@click.pass_context
# Example UUID: 'fadfcc38-5d42-4857-a950-0adc65babb13'
def fixup_user(ctx, uuid):
    """Fix a single employee."""
    mo_employees = [ctx.obj["mora_helper"].read_user(user_uuid=uuid)]
    fixup(ctx.obj, mo_employees)


@cli.command()
@click.option(
    "--root-uuid", type=click.UUID, help="UUID of root SD org_unit", required=True
)
@click.option(
    "--client-id", envvar="CLIENT_ID", help="Keycloak client id", default="dipex"
)
@click.option(
    "--client-secret",
    envvar="CLIENT_SECRET",
    help="Keycloak client secret",
)
@click.option(
    "--auth-realm", envvar="AUTH_REALM", help="Keycloak auth realm", default="mo"
)
@click.option(
    "--auth-server",
    envvar="AUTH_SERVER",
    help="Keycloak auth server",
    default="http://localhost:5000/auth",
)
@click.pass_context
def fixup_associations(
    ctx, root_uuid, client_id, client_secret, auth_realm, auth_server
):
    """Ensure all associations are of the type "SD-medarbejder"."""
    mora_helper = ctx.obj["mora_helper"]
    org = mora_helper.read_organisation()

    org_units = mora_helper.read_ou_root(org, str(root_uuid))
    org_unit_uuids = [o["uuid"] for o in org_units]

    association_type_uuid = mora_helper.ensure_class_in_facet(
        "association_type", "SD-Medarbejder"
    )

    with GraphQLClient(
        url=f"{ctx.obj['mora_base']}/graphql/v3",
        client_id=client_id,
        client_secret=client_secret,
        auth_realm=auth_realm,
        auth_server=auth_server,
        sync=True,
        httpx_client_kwargs={"timeout": None},
    ) as session:
        associations = read_associations(session, org_unit_uuids)
        filtered_associations = {
            a["uuid"]: a["validity"]["from"]
            for a in associations
            if a["association_type_uuid"] != str(association_type_uuid)
        }
        if ctx.obj["dry_run"]:
            click.echo(
                f"Found {len(list(filtered_associations))} associations that needs to be changed."  # noqa
            )
            click.echo(filtered_associations.keys())
            return
        for uuid, from_date in filtered_associations.items():
            try:
                fix_association_types(
                    session=session,
                    association_uuid=uuid,
                    from_date=from_date,
                    correct_association_type_uuid=association_type_uuid,
                )
            except:  # noqa
                click.echo(f"Error processing association with {uuid=}")


@cli.command()
@click.option(
    "--mox-base",
    default=load_setting("mox.base", "http://localhost:5000/lora"),
    help="URL for Lora",
)
@click.pass_context
def fixup_leaves(ctx, mox_base):
    """Fix all leaves that are missing a link to an engagement."""

    mora_helper = ctx.obj["mora_helper"]
    settings: Settings = ctx["settings"]

    # Find all classes of leave_types
    leave_types, _ = mora_helper.read_classes_in_facet("leave_type")
    leave_type_uuids = map(itemgetter("uuid"), leave_types)

    # Get all leave objects
    orgfunc_getter = partial(get_orgfunc_from_vilkaarligrel, mox_base=mox_base)
    leave_objects = map(orgfunc_getter, leave_type_uuids)
    leave_objects = list(flatten(leave_objects))

    # Filter to get only those missing the 'engagement'.
    leave_objects = list(filter(filter_missing_data, leave_objects))
    leave_uuids = set(map(itemgetter("id"), leave_objects))
    # Delete old leave objects
    if ctx.obj["dry_run"]:
        click.echo(f"Dry-run. Would delete {len(leave_uuids)} leave objects")
    else:
        orgfunc_deleter = partial(delete_orgfunc, mox_base=mox_base)
        leave_uuids = tqdm(
            leave_uuids,
            unit="leave",
            desc="Deleting old leaves",
            disable=not ctx.obj["progress"],
        )
        consume(side_effect(orgfunc_deleter, leave_uuids))

    # Find all user uuids and cprs
    user_uuids = set(map(get_user_from_org_func, leave_objects))
    user_uuids = tqdm(
        user_uuids,
        unit="user",
        desc="Looking up users in MO",
        disable=not ctx.obj["progress"],
    )
    users = map(mora_helper.read_user, user_uuids)
    cpr_uuid_map = dict(map(itemgetter("cpr_no", "uuid"), users))
    # NOTE: This will only reimport current leaves, not historic ones
    #       This behavior is inline with sd_importer.py
    assert isinstance(settings.sd_institution_identifier, str)
    changed_at = ChangeAtSD(
        settings, settings.sd_institution_identifier, datetime.datetime.now()
    )

    def try_fetch_leave(cpr: str) -> Tuple[str, List[dict]]:
        """Attempt to lookup engagements from a CPR.

        Prints any errors but continues
        """
        employments = []
        try:
            employments = fetch_user_employments(settings, cpr=cpr)
        except Exception as e:
            click.echo(e)
        # filter leaves
        leaves = list(
            filter(
                lambda employment: EmploymentStatus(
                    employment["EmploymentStatus"]["EmploymentStatusCode"]
                )
                == EmploymentStatus.Orlov,
                employments,
            )
        )
        return cpr, leaves

    cprs = tqdm(
        cpr_uuid_map.keys(),
        desc="Lookup users in SD",
        unit="User",
        disable=not ctx.obj["progress"],
    )
    leaves = dict(map(try_fetch_leave, cprs))

    # Filter users with leave
    leaves = dict(filter(apply(lambda cpr, engagement: engagement), leaves.items()))

    if ctx.obj["dry_run"]:
        click.echo(f"Dry-run. Would reimport leaves for {len(leaves)} users.")
        return

    for cpr, leaves in tqdm(
        leaves.items(),
        unit="user",
        desc="Reimporting leaves for users",
        disable=not ctx.obj["progress"],
    ):
        for leave in leaves:
            changed_at.create_leave(
                leave["EmploymentStatus"],
                leave["EmploymentIdentifier"],
                cpr_uuid_map[cpr],
            )


@cli.command()
@click.option(
    "--uuid", type=click.UUID, help="UUID of the organisation to check.", required=True
)
@click.pass_context
# Example UUID: 'ea5a237a-8f8b-4300-9a00-000006180002'
def fixup_department(ctx, uuid):
    """Fix all employees in an organisation."""
    mo_employees = (
        ctx.obj["mora_helper"].read_organisation_people(uuid, read_all=True).keys()
    )
    fixup(ctx.obj, mo_employees)


@cli.command()
@click.option(
    "--limit",
    type=click.INT,
    help="Number of employees to check. 0 --> All.",
    default=5,
)
@click.pass_context
def fixup_all(ctx, limit):
    """Fix limit/all employees in an MO instance."""
    mo_employees = ctx.obj["mora_helper"].read_all_users(limit=limit)
    fixup(ctx.obj, mo_employees)


if __name__ == "__main__":
    cli()
