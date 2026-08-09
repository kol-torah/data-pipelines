"""Standalone Streamlit CRUD page for rabbis and series.

Not part of the lab (documents/design.md §8) — that's a separate, not-yet-built
Streamlit app that reads the runs tables. This talks directly to the production
database, since rabbis/series are catalogue data, not experiment data. See
documents/database-schema.md §5 ("Admin interface for adding rabbis/series").

Run with: uv run streamlit run src/data_pipelines/admin_app.py
"""

import pandas as pd
import streamlit as st
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from data_pipelines.config import get_settings
from data_pipelines.db import Rabbi, Series

st.set_page_config(page_title="Kol Torah — Rabbis & Series Admin", layout="wide")


@st.cache_resource
def get_engine() -> Engine:
    return create_engine(get_settings().database_url())


def rabbis_tab(session: Session) -> None:
    st.subheader("Rabbis")
    rabbis = session.scalars(select(Rabbi).order_by(Rabbi.name_en)).all()

    if rabbis:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": r.id,
                        "Name (he)": r.name_he,
                        "Name (en)": r.name_en,
                        "Slug": r.slug,
                        "Series": len(r.series),
                    }
                    for r in rabbis
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No rabbis yet.")

    with st.expander("Add rabbi"):
        with st.form("add_rabbi", clear_on_submit=True):
            name_he = st.text_input("Name (Hebrew)")
            name_en = st.text_input("Name (English)")
            slug = st.text_input("Slug")
            if st.form_submit_button("Add"):
                if not (name_he and name_en and slug):
                    st.error("All fields are required.")
                else:
                    session.add(Rabbi(name_he=name_he, name_en=name_en, slug=slug))
                    try:
                        session.commit()
                        st.success(f"Added {name_en}.")
                        st.rerun()
                    except IntegrityError:
                        session.rollback()
                        st.error(f"Slug '{slug}' is already in use.")

    if not rabbis:
        return

    with st.expander("Edit / delete rabbi"):
        options = {f"{r.name_en} ({r.slug})": r.id for r in rabbis}
        choice = st.selectbox("Rabbi", options.keys(), key="rabbi_edit_choice")
        rabbi = session.get(Rabbi, options[choice])
        assert rabbi is not None

        with st.form("edit_rabbi"):
            name_he = st.text_input("Name (Hebrew)", value=rabbi.name_he)
            name_en = st.text_input("Name (English)", value=rabbi.name_en)
            slug = st.text_input("Slug", value=rabbi.slug)
            col1, col2 = st.columns(2)
            save = col1.form_submit_button("Save changes")
            delete = col2.form_submit_button("Delete")

            if save:
                rabbi.name_he, rabbi.name_en, rabbi.slug = name_he, name_en, slug
                try:
                    session.commit()
                    st.success("Saved.")
                    st.rerun()
                except IntegrityError:
                    session.rollback()
                    st.error(f"Slug '{slug}' is already in use.")

            if delete:
                series_count = session.scalar(
                    select(func.count()).select_from(Series).where(Series.rabbi_id == rabbi.id)
                )
                if series_count:
                    st.error(f"Cannot delete {rabbi.name_en}: still has {series_count} series.")
                else:
                    session.delete(rabbi)
                    session.commit()
                    st.success("Deleted.")
                    st.rerun()


def series_tab(session: Session) -> None:
    st.subheader("Series")
    rabbis = session.scalars(select(Rabbi).order_by(Rabbi.name_en)).all()
    if not rabbis:
        st.info("Add a rabbi first.")
        return

    series = session.scalars(select(Series).order_by(Series.name_en)).all()
    if series:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": s.id,
                        "Rabbi": s.rabbi.name_en,
                        "Name (he)": s.name_he,
                        "Name (en)": s.name_en,
                        "Slug": s.slug,
                        "Lesson type": s.lesson_type,
                        "Adapter key": s.adapter_key,
                        "Lessons": len(s.lessons),
                    }
                    for s in series
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No series yet.")

    rabbi_options = {f"{r.name_en} ({r.slug})": r.id for r in rabbis}

    with st.expander("Add series"):
        with st.form("add_series", clear_on_submit=True):
            rabbi_choice = st.selectbox("Rabbi", rabbi_options.keys())
            name_he = st.text_input("Name (Hebrew)")
            name_en = st.text_input("Name (English)")
            slug = st.text_input("Slug")
            lesson_type = st.text_input("Lesson type")
            adapter_key = st.text_input("Adapter key")
            description_he = st.text_area("Description (Hebrew)")
            description_en = st.text_area("Description (English)")
            if st.form_submit_button("Add"):
                if not (name_he and name_en and slug and lesson_type and adapter_key):
                    st.error("Name, slug, lesson type, and adapter key are required.")
                else:
                    session.add(
                        Series(
                            rabbi_id=rabbi_options[rabbi_choice],
                            name_he=name_he,
                            name_en=name_en,
                            slug=slug,
                            lesson_type=lesson_type,
                            adapter_key=adapter_key,
                            description_he=description_he or None,
                            description_en=description_en or None,
                        )
                    )
                    try:
                        session.commit()
                        st.success(f"Added {name_en}.")
                        st.rerun()
                    except IntegrityError:
                        session.rollback()
                        st.error(f"Slug '{slug}' is already in use.")

    if not series:
        return

    with st.expander("Edit / delete series"):
        series_options = {f"{s.name_en} — {s.rabbi.name_en} ({s.slug})": s.id for s in series}
        choice = st.selectbox("Series", series_options.keys(), key="series_edit_choice")
        item = session.get(Series, series_options[choice])
        assert item is not None

        with st.form("edit_series"):
            rabbi_choice = st.selectbox(
                "Rabbi",
                rabbi_options.keys(),
                index=list(rabbi_options.values()).index(item.rabbi_id),
            )
            name_he = st.text_input("Name (Hebrew)", value=item.name_he)
            name_en = st.text_input("Name (English)", value=item.name_en)
            slug = st.text_input("Slug", value=item.slug)
            lesson_type = st.text_input("Lesson type", value=item.lesson_type)
            adapter_key = st.text_input("Adapter key", value=item.adapter_key)
            description_he = st.text_area("Description (Hebrew)", value=item.description_he or "")
            description_en = st.text_area("Description (English)", value=item.description_en or "")
            col1, col2 = st.columns(2)
            save = col1.form_submit_button("Save changes")
            delete = col2.form_submit_button("Delete")

            if save:
                item.rabbi_id = rabbi_options[rabbi_choice]
                item.name_he, item.name_en, item.slug = name_he, name_en, slug
                item.lesson_type, item.adapter_key = lesson_type, adapter_key
                item.description_he = description_he or None
                item.description_en = description_en or None
                try:
                    session.commit()
                    st.success("Saved.")
                    st.rerun()
                except IntegrityError:
                    session.rollback()
                    st.error(f"Slug '{slug}' is already in use.")

            if delete:
                lesson_count = len(item.lessons)
                if lesson_count:
                    st.error(f"Cannot delete {item.name_en}: still has {lesson_count} lessons.")
                else:
                    session.delete(item)
                    session.commit()
                    st.success("Deleted.")
                    st.rerun()


def main() -> None:
    st.title("Kol Torah — Rabbis & Series Admin")
    with Session(get_engine()) as session:
        rabbis_tab_ui, series_tab_ui = st.tabs(["Rabbis", "Series"])
        with rabbis_tab_ui:
            rabbis_tab(session)
        with series_tab_ui:
            series_tab(session)


main()
