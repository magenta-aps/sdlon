# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from sqlalchemy import Column, String
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func


Base = declarative_base()


class Payload(Base):  # type: ignore
    __tablename__ = "payload"

    id = Column(UUID(as_uuid=True), primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    full_url = Column(TEXT)
    params = Column(TEXT)
    response = Column(TEXT)
    status_code = Column(Integer)


class Runs(Base):  # type: ignore
    __tablename__ = "runs"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    from_date = Column("from_date", DateTime(timezone=True))
    to_date = Column("to_date", DateTime(timezone=True))
    status = Column("status", String(60))
