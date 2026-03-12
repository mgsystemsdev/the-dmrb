"""DMRB AI Agent screen: chat sessions and messages."""
from __future__ import annotations

import json
from typing import Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

import streamlit as st


def _chat_api_base_url() -> str:
    import os

    return (
        os.environ.get("DMRB_CHAT_API_BASE_URL") or "http://127.0.0.1:8000"
    ).rstrip("/")


def _chat_api_request(method: str, path: str, payload: Optional[dict] = None):
    url = f"{_chat_api_base_url()}{path}"
    headers = {"Content-Type": "application/json"}
    body = (
        json.dumps(payload).encode("utf-8") if payload is not None else None
    )
    req = urllib_request.Request(
        url, data=body, headers=headers, method=method.upper()
    )
    try:
        with urllib_request.urlopen(req, timeout=90) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(
            f"Could not reach chat API at {_chat_api_base_url()}"
        ) from exc


def render() -> None:
    st.subheader("DMRB AI Agent")
    st.caption("AI can make mistakes. Check important info.")

    if "ai_current_session_id" not in st.session_state:
        st.session_state.ai_current_session_id = None
    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = []

    fallback_suggestions = [
        "How many units are vacant right now?",
        "Which units are about to breach SLA?",
        "Who has the most open units?",
        "Give me a morning briefing",
    ]

    try:
        sessions = _chat_api_request("GET", "/api/chat/sessions") or []
    except Exception as exc:
        st.error(str(exc))
        sessions = []

    left, right = st.columns([1, 3], gap="small")
    with left:
        if st.button("+ New Chat", use_container_width=True):
            st.session_state.ai_current_session_id = None
            st.session_state.ai_messages = []
            st.rerun()
        st.markdown("#### Sessions")
        if not sessions:
            st.caption("No chat sessions yet.")
        for session in sessions:
            sid = session.get("session_id")
            title = session.get("title") or "New Chat"
            row_a, row_b = st.columns([4, 1], gap="small")
            selected = st.session_state.ai_current_session_id == sid
            if row_a.button(
                f"{'● ' if selected else ''}{title[:40]}",
                key=f"ai_open_{sid}",
                use_container_width=True,
            ):
                st.session_state.ai_current_session_id = sid
                try:
                    st.session_state.ai_messages = (
                        _chat_api_request(
                            "GET",
                            f"/api/chat/sessions/{sid}/messages",
                        )
                        or []
                    )
                except Exception as exc:
                    st.error(str(exc))
                st.rerun()
            if row_b.button("🗑", key=f"ai_del_{sid}", use_container_width=True):
                try:
                    _chat_api_request("DELETE", f"/api/chat/sessions/{sid}")
                    if st.session_state.ai_current_session_id == sid:
                        st.session_state.ai_current_session_id = None
                        st.session_state.ai_messages = []
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with right:
        current_session_id = st.session_state.ai_current_session_id
        if current_session_id and not st.session_state.ai_messages:
            try:
                st.session_state.ai_messages = (
                    _chat_api_request(
                        "GET",
                        f"/api/chat/sessions/{current_session_id}/messages",
                    )
                    or []
                )
            except Exception as exc:
                st.error(str(exc))

        if not st.session_state.ai_messages:
            st.markdown("### DMRB AI Agent")
            try:
                suggestions = (
                    _chat_api_request("GET", "/api/chat/suggestions")
                    or fallback_suggestions
                )
            except Exception:
                suggestions = fallback_suggestions
            cols = st.columns(2)
            for idx, question in enumerate(suggestions[:10]):
                if cols[idx % 2].button(
                    question, key=f"ai_suggest_{idx}", use_container_width=True
                ):
                    st.session_state.ai_input_prefill = question
                    st.rerun()

        for message in st.session_state.ai_messages:
            role = (
                "assistant"
                if message.get("role") == "assistant"
                else "user"
            )
            with st.chat_message(role):
                st.markdown(message.get("content") or "")

        prompt = st.chat_input("Ask anything about turnovers...")
        if prompt is None and st.session_state.get("ai_input_prefill"):
            prompt = st.session_state.pop("ai_input_prefill")
        if prompt:
            with st.chat_message("user"):
                st.markdown(prompt)
            try:
                response = _chat_api_request(
                    "POST",
                    "/api/chat",
                    {
                        "sessionId": current_session_id or "new",
                        "message": prompt,
                    },
                )
                new_session_id = (
                    response.get("sessionId")
                    if isinstance(response, dict)
                    else None
                )
                if new_session_id:
                    st.session_state.ai_current_session_id = new_session_id
                    st.session_state.ai_messages = (
                        _chat_api_request(
                            "GET",
                            f"/api/chat/sessions/{new_session_id}/messages",
                        )
                        or []
                    )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
