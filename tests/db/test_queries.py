from datetime import datetime
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine, desc, select
from sqlalchemy.orm import Session

from db.models import Base, Runs
from db.queries import get_run_db_from_date, delete_last_run
from db.queries import get_status
from db.queries import persist_status
from sdlon.metrics import RunDBState


@patch("db.queries.get_engine")
def test_persist_and_get_status(mock_get_engine: MagicMock):
    # Arrange
    engine = create_engine("sqlite:///:memory:")
    mock_get_engine.return_value = engine

    Base.metadata.tables["runs"].create(bind=engine)
    from_date = datetime(2000, 1, 1, 12, 0, 0)
    to_date = datetime(2001, 1, 1, 12, 0, 0)

    # Act
    persist_status(datetime.now(), datetime.now(), RunDBState.COMPLETED)
    persist_status(from_date, to_date, RunDBState.RUNNING)
    status = get_status()

    with Session(engine) as session:
        statement = select(Runs.from_date, Runs.to_date).order_by(desc(Runs.id)).limit(1)
        actual_from_date, actual_to_date = session.execute(statement).fetchone()

    # Assert
    assert status == RunDBState.RUNNING
    assert from_date == actual_from_date
    assert to_date == actual_to_date


@patch("db.queries.get_engine")
def test_get_status_is_unknown_for_unknown_run_state(mock_get_engine: MagicMock):
    # Arrange
    engine = create_engine("sqlite:///:memory:")
    mock_get_engine.return_value = engine

    Base.metadata.tables["runs"].create(bind=engine)

    # Act
    with Session(engine) as session:
        run = Runs(from_date=datetime.now(), to_date=datetime.now(), status="xyz")
        session.add(run)
        session.commit()
    status = get_status()

    # Assert
    assert status == RunDBState.UNKNOWN


@patch("db.queries.get_engine", return_value=create_engine("sqlite:///:memory:"))
def test_get_status_is_completed_for_empty_table(mock_get_engine: MagicMock):
    # Arrange
    engine = mock_get_engine()
    Base.metadata.tables["runs"].create(bind=engine)

    # Act
    status = get_status()

    # Assert
    assert status == RunDBState.COMPLETED


@patch("db.queries.Session")
def test_get_status_return_unknown_on_error(mock_session: MagicMock):
    # Arrange
    mock_session.side_effect = Exception()

    # Act
    status = get_status()

    # Assert
    assert status == RunDBState.UNKNOWN


@patch("db.queries.get_engine")
def test_get_run_db_from_date(mock_get_engine: MagicMock):
    # Arrange
    engine = create_engine("sqlite:///:memory:")
    mock_get_engine.return_value = engine

    Base.metadata.tables["runs"].create(bind=engine)
    from_date = datetime(2000, 1, 1, 12, 0, 0)
    to_date = datetime(2001, 1, 1, 12, 0, 0)

    # Act
    persist_status(from_date, to_date, RunDBState.RUNNING)
    persist_status(from_date, to_date, RunDBState.COMPLETED)
    actual_from_date = get_run_db_from_date()

    # Assert
    assert actual_from_date == to_date


@patch("db.queries.get_engine")
def test_delete_last_run(mock_get_engine: MagicMock) -> None:
    # Arrange
    engine = create_engine("sqlite:///:memory:")
    mock_get_engine.return_value = engine

    Base.metadata.tables["runs"].create(bind=engine)
    from_date = datetime(2000, 1, 1, 12, 0, 0)
    to_date = datetime(2001, 1, 1, 12, 0, 0)

    persist_status(from_date, to_date, RunDBState.COMPLETED)
    persist_status(from_date, to_date, RunDBState.RUNNING)

    # Act
    delete_last_run()

    # Assert
    status = get_status()
    assert status == RunDBState.COMPLETED
