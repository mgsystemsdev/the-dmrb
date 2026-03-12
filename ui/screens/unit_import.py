"""Unit Master Import screen: CSV bootstrap for units."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from ui.data.backend import (
    BACKEND_ERROR,
    db_repository,
    get_db_path,
    unit_master_import_service_mod,
)
from ui.data.cache import (
    cached_list_unit_master_import_units,
    db_available,
    db_cache_identity,
    db_write,
    render_active_property_banner,
)


def render() -> None:
    st.subheader("Unit Master Import")
    st.caption(
        "One-time structural bootstrap from Units.csv. Writes only to unit "
        "(and phase/building when creating units). Does not touch turnover, "
        "task, risk, or SLA."
    )
    if not unit_master_import_service_mod or not db_repository:
        st.warning("Backend or unit master import service not available.")
        if BACKEND_ERROR is not None:
            with st.expander("Details"):
                st.code(str(BACKEND_ERROR), language=None)
                st.caption("Run from repo root: streamlit run the-dmrb/app.py")
        return
    if not st.session_state.get("enable_db_writes"):
        st.warning("Enable DB Writes in the sidebar to run import.")
        return
    active_property = render_active_property_banner()
    if active_property is None:
        return
    if not db_available():
        st.error("Database not available")
        return
    db_identity = db_cache_identity()
    property_id = active_property["property_id"]
    strict_mode = st.checkbox(
        "Strict mode (fail if unit not found; no creates)",
        value=False,
        key="um_import_strict",
    )
    uploaded = st.file_uploader(
        "Units.csv", type=["csv"], key="um_import_file"
    )
    if st.button("Run Unit Master Import", key="um_import_run"):
        if uploaded is None:
            st.warning("Upload a CSV file first.")
        else:
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".csv", delete=False
            ) as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = tmp.name
            try:
                um_result = [None]

                def do_import(conn):
                    um_result[0] = (
                        unit_master_import_service_mod.run_unit_master_import(
                            conn,
                            tmp_path,
                            property_id=property_id,
                            strict_mode=strict_mode,
                        )
                    )

                if db_write(do_import):
                    result = um_result[0] or {}
                    status_label = result.get("status", "SUCCESS")
                    if status_label == "NO_OP":
                        st.info(
                            "No-op: this file was already imported (checksum match). Applied: 0"
                        )
                    else:
                        st.success(
                            f"Status: {status_label} | Applied: {result.get('applied_count', 0)} | "
                            f"Conflicts: {result.get('conflict_count', 0)} | Errors: {result.get('error_count', 0)}"
                        )
                    if result.get("errors"):
                        for err in result["errors"][:20]:
                            st.write(f"- {err}")
                        if len(result["errors"]) > 20:
                            st.caption(
                                f"... and {len(result['errors']) - 20} more."
                            )
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    st.markdown("### Unit Master Import — Imported Units")
    imported_units = cached_list_unit_master_import_units(db_identity)
    if imported_units:
        st.dataframe(
            pd.DataFrame(imported_units),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No units imported yet.")
