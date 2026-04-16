import click

from .sd_changed_at import changed_at_cli
from .sd_changed_at_redo import cli as changed_at_redo
from .test_mo_against_sd import cli as mo_against_sd


@click.group()
def SDTool():
    """Common entrypoint to SD programs."""
    pass


SDTool.add_command(mo_against_sd, "test_mo_against_sd")
SDTool.add_command(changed_at_cli)
SDTool.add_command(changed_at_redo)

if __name__ == "__main__":
    SDTool()
