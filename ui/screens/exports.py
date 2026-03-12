"""Exports screen: prepare and download report artifacts."""
from __future__ import annotations

from datetime import date

import streamlit as st

from ui.data.backend import export_service_mod, get_conn
from ui.data.cache import render_active_property_banner


def render() -> None:
    st.subheader("Export Reports")
    st.caption(
        "Exports always include all open turnovers (closed/canceled excluded), "
        "regardless of current screen filters."
    )
    if render_active_property_banner() is None:
        return
    if not export_service_mod:
        st.warning("Export service is not available.")
        return

    if "export_payloads" not in st.session_state:
        st.session_state.export_payloads = None

    conn = get_conn()
    if not conn:
        st.error("Database not available")
        return
    try:
        if st.button("Prepare Export Files", key="prepare_exports"):
            with st.spinner("Building reports..."):
                st.session_state.export_payloads = (
                    export_service_mod.generate_all_export_artifacts(
                        conn, today=date.today()
                    )
                )
            st.success("Export files ready.")
    except Exception as e:
        st.error(str(e))
    finally:
        conn.close()

    payloads = st.session_state.export_payloads
    if not payloads:
        st.info("Click 'Prepare Export Files' to generate downloads.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download Final Report (XLSX)",
            data=payloads.get("Final_Report.xlsx", b""),
            file_name="Final_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_final_xlsx",
        )
        st.download_button(
            "Download DMRB Report (XLSX)",
            data=payloads.get("DMRB_Report.xlsx", b""),
            file_name="DMRB_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_dmrb_xlsx",
        )
        st.download_button(
            "Download Dashboard Chart (PNG)",
            data=payloads.get("Dashboard_Chart.png", b""),
            file_name="Dashboard_Chart.png",
            mime="image/png",
            key="dl_dashboard_png",
        )
    with c2:
        st.download_button(
            "Download Weekly Summary (TXT)",
            data=payloads.get("Weekly_Summary.txt", b""),
            file_name="Weekly_Summary.txt",
            mime="text/plain",
            key="dl_weekly_txt",
        )
        st.download_button(
            "Download All Reports (ZIP)",
            data=payloads.get("DMRB_Reports.zip", b""),
            file_name="DMRB_Reports.zip",
            mime="application/zip",
            key="dl_all_zip",
        )
