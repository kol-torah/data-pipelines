"""Shape of the version-controlled catalogue seed file — see export_catalogue.py."""

from pydantic import BaseModel


class SeriesSeed(BaseModel):
    slug: str
    name_he: str
    name_en: str
    lesson_type: str
    adapter_key: str
    description_he: str | None = None
    description_en: str | None = None


class RabbiSeed(BaseModel):
    slug: str
    name_he: str
    name_en: str
    series: list[SeriesSeed] = []


class CatalogueSeed(BaseModel):
    rabbis: list[RabbiSeed]
