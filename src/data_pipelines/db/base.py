from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, Text
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names, so Alembic autogenerate produces stable, diffable
# migrations instead of driver-assigned names like "postgres_id_fkey1".
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Repo-wide column type defaults, so models say `Mapped[str]` / `Mapped[datetime]`
    # and get TEXT / TIMESTAMPTZ / BIGINT rather than VARCHAR / naive TIMESTAMP / INTEGER.
    type_annotation_map = {
        str: Text,
        datetime: DateTime(timezone=True),
        int: BigInteger,
    }
