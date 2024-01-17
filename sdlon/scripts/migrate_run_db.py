from datetime import datetime, timezone

import click
from sqlalchemy import create_engine, select, insert
from sqlalchemy.orm import Session

from db.engine import get_engine
from db.models import Runs


def read_from_sqlite():
    engine = create_engine("sqlite:///run_db.sqlite")
    with Session(engine) as session:
        statement = select(Runs.from_date, Runs.to_date, Runs.status).order_by(Runs.id)
        rows = session.execute(statement).fetchall()
        for from_date, to_date, status in rows:
            yield from_date.replace(tzinfo=timezone.utc), to_date.replace(tzinfo=timezone.utc), status


def write_to_postgres(from_date: datetime, to_date: datetime, status: str):
    engine = get_engine()
    if "Running" in status:
        status = "running"
    elif "Update" in status:
        status = "ok"
    else:
        return
    with Session(engine) as session:
        statement = insert(Runs).values(from_date=from_date, to_date=to_date, status=status)
        session.execute(statement)
        session.commit()


@click.command()
def main():
    for from_date, to_date, status in read_from_sqlite():
        print(repr(from_date), repr(to_date), status)
        write_to_postgres(from_date, to_date, status)


if __name__ == "__main__":
    main()
