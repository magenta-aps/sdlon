import click

from .sd_changed_at import changed_at_cli
from .sd_changed_at_redo import cli as changed_at_redo
from .sd_fixup import cli as sd_fixup
from .sd_importer import cli as sd_importer
from .sync_job_id import sync_jobid
from .test_mo_against_sd import cli as mo_against_sd


@click.group()
def SDTool():
    """Common entrypoint to SD programs."""
    pass


SDTool.add_command(sd_importer, "sd_importer")
SDTool.add_command(mo_against_sd, "test_mo_against_sd")
SDTool.add_command(sync_jobid)
SDTool.add_command(changed_at_cli)
SDTool.add_command(changed_at_redo)
SDTool.add_command(sd_fixup)


if __name__ == "__main__":
    SDTool()
