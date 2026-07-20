"""Story Summary page — pick a customer, language, and provider; get six stories.

A pure consumer of the cleaned DataFrame staged by the Home page. Generation is
**explicitly triggered**: the controls sit in an ``st.form``, so changing a
dropdown costs nothing and no API call happens until the user presses *Generate
stories*. The submitted request is remembered in ``session_state`` so incidental
reruns (a download click, an expander) re-render from cache instead of
re-billing, and a newly uploaded file clears the request rather than silently
regenerating against different data.

The heavy work (six grounded LLM summaries) is wrapped in ``@st.cache_data``
keyed on the data, customer, product, language, and provider. The engine itself
is Streamlit-free (``summarizer.py``); this page only owns the widgets, the
cache key, and the render call.
"""

from __future__ import annotations

import streamlit as st

from src import consts, state, version
from src.engine import fallback
from src.engine.providers import available_providers, build_with_fallback
from src.engine.summarizer import summarize_product
from src.pipeline import mapping
from src.report import story_report
from src.ui import components, story_view

st.set_page_config(page_title="Story Summary", page_icon="📖", layout="wide")
components.theme_hint()
st.title("📖 Story Summary")

df = state.require_data()  

REQUEST_KEY = "story_request"


def _provider_selector(names: list[str]) -> str:
    """Dropdown of providers that can actually run (key + SDK present)."""
    default = consts.DEFAULT_PROVIDER if consts.DEFAULT_PROVIDER in names else names[0]

    def label(n: str) -> str:
        return f"{n} · {consts.PROVIDER_MODELS.get(n, n)}"

    return st.selectbox("Provider", names, index=names.index(default),
                        format_func=label, key="provider")


providers_available = available_providers()

with st.form("story_controls"):
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        customer = components.customer_selector(df)
    with c2:
        language = components.language_toggle()
    with c3:
        if providers_available:
            provider_name = _provider_selector(providers_available)
        else:
            provider_name = None
            st.selectbox("Provider", ["(none configured)"], disabled=True)

    submitted = st.form_submit_button("✨ Generate stories", type="primary")

if not providers_available:
    st.info("No LLM provider configured — generating will show a **deterministic, "
            "factual view** built directly from the tickets (real timeframes, "
            "ticket numbers, outcomes). Add a key in `.streamlit/secrets.toml`, "
            "**or run a local model with Ollama** (free, offline), for narrated "
            "storytelling summaries.")

if submitted:
    st.session_state[REQUEST_KEY] = {
        "customer": customer,
        "language": language,
        "provider": provider_name,
        "source": state.get_source_name(), 
    }

request = st.session_state.get(REQUEST_KEY)
if request is not None and request["source"] != state.get_source_name():
    st.session_state.pop(REQUEST_KEY, None)
    request = None

if request is None:
    st.info("Choose a customer, language, and provider above, then press "
            "**Generate stories**. Nothing is sent to a provider until you do.")
    st.stop()

customer = request["customer"]
language = request["language"]
provider_name = request["provider"]


@st.cache_data(show_spinner=False)
def _generate_product(df, customer: str, product: str, language: str,
                      provider_name: str | None, _code: str):
    """One product's summary + its fallback trace."""
    provider = build_with_fallback(provider_name)
    subset = df[(df[consts.OUT_CUSTOMER] == customer)
                & (df[consts.OUT_PRODUCT] == product)]
    summary = summarize_product(subset if len(subset) else None,
                                product, language, provider)
    return summary, list(getattr(provider, "trace", []))


def _clear_current_request() -> None:
    """Drop only THIS request's cache entries, not every customer's.

    ``.clear(*args)`` evicts a single memoized entry; older Streamlit builds can
    only clear the whole function, so fall back to that.
    """
    try:
        for product in consts.PRODUCTS:
            _generate_product.clear(df, customer, product, language, provider_name,
                                    version.code_fingerprint())
    except TypeError:
        _generate_product.clear()


if st.button("↻ Regenerate", help="Discard this customer's cached stories and "
                                  "re-run them — this re-bills the provider"):
    _clear_current_request()

cust_df = df[df[consts.OUT_CUSTOMER] == customer]
active = [p for p in consts.PRODUCTS
          if len(cust_df[cust_df[consts.OUT_PRODUCT] == p])]
story_view.render_header(customer, active, len(cust_df))

if not active:
    st.stop()


summaries: dict = {}
trace: list[str] = []
n = len(consts.PRODUCTS)
progress = st.progress(0.0, text="Starting…")
for i, product in enumerate(consts.PRODUCTS):
    progress.progress(i / n, text=f"Generating {product}… ({i + 1}/{n})")
    summary, product_trace = _generate_product(df, customer, product, language,
                                               provider_name,
                                               version.code_fingerprint())
    summaries[product] = summary
    trace.extend(product_trace)
    story_view.render_product_section(
        product, summary, cust_df[cust_df[consts.OUT_PRODUCT] == product],
        language)
progress.empty()

served = sorted({s.provider for s in summaries.values() if s.provider})
if provider_name and fallback.PROVIDER_LABEL in served:
    st.warning(f"Some products couldn't be narrated by **{provider_name}** and "
               "fell back to a **factual, non-narrated view** — see the fallback "
               "trace below.")

categories = mapping.ticket_categories(cust_df)

with st.container(horizontal=True):
    st.download_button(
        "⬇ Download report (HTML)",
        data=story_report.build(summaries, customer, language, categories),
        file_name=f"story_{customer}_{language.lower()}.html",
        mime="text/html",
        type="primary",
        help="A standalone, styled document — no internet needed to open it, "
             "and it prints straight to PDF from any browser.",
    )
    st.download_button(
        "⬇ Download story (Markdown)",
        data=story_view.to_markdown(summaries, customer, categories, language),
        file_name=f"story_{customer}_{language.lower()}.md",
        mime="text/markdown",
        help="Plain text, for pasting into a ticket, wiki, or commit message.",
    )

if trace:
    with st.expander("Provider fallback trace"):
        st.caption("A provider was skipped on a transport failure (timeout / "
                   "rate-limit / missing key) and the next one served.")
        for line in dict.fromkeys(trace):
            st.write("•", line)
