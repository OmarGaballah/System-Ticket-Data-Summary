"""Insights page — deterministic business analysis of the ticket data.

A pure consumer of the cleaned DataFrame staged by the Home page. Every number
is computed in pandas (``analysis/insights.py``); this page only lays out the KPI
row and one card per insight — a chart plus the data-derived recommendation. The
analysis is generic (it re-derives on any data), so the same page works whether
32 or 32,000 tickets are loaded.
"""

from __future__ import annotations

import streamlit as st

from src import state, version
from src.analysis import exec_summary, insights
from src.engine.providers import available_providers
from src.report import insights_report
from src.structs import DETERMINISTIC_PROVIDER
from src.ui import charts, components

st.set_page_config(page_title="Insights", page_icon="📊", layout="wide")
components.theme_hint()
st.title("📊 Insights")
st.caption("Operational analysis — each finding pairs a metric with a recommended action.")

df = state.require_data()  


@st.cache_data(show_spinner="Analysing tickets…")
def _analyse(data, _code: str):
    return insights.headline_kpis(data), insights.compute_all(data)


kpis, results = _analyse(df, version.code_fingerprint())

with st.container(horizontal=True):
    st.metric("Tickets", kpis["tickets"], border=True)
    st.metric("Customers", kpis["customers"], border=True)
    st.metric("Repeat-contact rate", f"{kpis['repeat_rate']:.0%}", border=True,
              help=f"{kpis['repeat_occasions']} of {kpis['contact_occasions']} "
                   f"contact occasions were a customer coming back about the "
                   f"same product. Tickets raised together count once.")
    st.metric("Escalation rate", f"{kpis['escalation_rate']:.0%}", border=True)
    st.metric(f"Top cause: {kpis['top_theme']}", f"{kpis['top_theme_pct']:.0%}", border=True)

st.info(
    f"This is a {kpis['tickets']}-ticket demonstration sample. The metrics and "
    "recommendations are computed generically — the same analysis scales to any "
    "volume, and each finding re-derives from whatever data is loaded.",
    icon=":material/info:",
)

REQUEST_KEY = "exec_request"


@st.cache_data(show_spinner="Writing executive summary…")
def _summary(data, provider_name, _code: str):
    k = insights.headline_kpis(data)
    items = insights.compute_all(data)
    return exec_summary.generate(k, items, provider_name)


written = None

for ins in results:
    with st.container(border=True):
        st.subheader(ins.title)
        st.caption(ins.question)
        if ins.has_signal:
            st.altair_chart(charts.insight_chart(ins), width="stretch", theme="streamlit")
        st.markdown(f"**So what →** {ins.takeaway}")
        with st.expander("Show data"):
            st.dataframe(ins.data, hide_index=True, width="stretch")

with st.container(border=True):
    head, pick = st.columns([3, 1])
    head.subheader("Executive summary")
    provs = available_providers()
    with pick:
        writer = st.selectbox("Written by", provs or [DETERMINISTIC_PROVIDER],
                              disabled=not provs, key="exec_writer")
    provider_name = writer if provs else None

    write_it = st.button("✍ Write summary", type="primary", key="write_summary")
    if write_it:
        st.session_state[REQUEST_KEY] = {"provider": provider_name,
                                         "source": state.get_source_name()}

    request = st.session_state.get(REQUEST_KEY)
    if request is not None and request["source"] != state.get_source_name():
        st.session_state.pop(REQUEST_KEY, None)
        request = None

    if request is None:
        st.caption("Every metric on this page is computed deterministically in "
                   "pandas. Press **Write summary** to have the selected "
                   "provider narrate those findings — that is the only call "
                   "this page makes.")
    else:
        provider_name = request["provider"]
        if st.button("↻ Regenerate", key="regen_summary",
                     help="Re-run the summary — this re-bills the provider"):
            try:
                _summary.clear(df, provider_name, version.code_fingerprint())
            except TypeError:
                _summary.clear()
        es = written = _summary(df, provider_name, version.code_fingerprint())

        st.markdown(es.summary)
        if es.top_actions:
            st.markdown("**Priorities**")
            for action in es.top_actions:
                st.markdown(f"- {action}")
        st.caption(es.attribution() + (f" {es.note}" if es.note else ""))

st.download_button(
    "⬇ Download this report (HTML)",
    data=insights_report.build(kpis, results, written, state.get_source_name()),
    file_name="ticket_insights.html",
    mime="text/html",
    type="primary",
    help="A standalone, styled document — charts included, nothing fetched from "
         "the internet. Opens anywhere, and prints straight to PDF from any browser.",
)
if written is None:
    st.caption("The report will include the executive summary if you write one first.")
