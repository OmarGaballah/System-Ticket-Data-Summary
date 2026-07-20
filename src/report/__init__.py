"""Self-contained HTML reports.

Pure builders — every module here turns already-computed objects into an HTML
string with no Streamlit import, exactly like ``src/pipeline/export.py``. The
pages own the ``st.download_button``; these modules own the document.

The output is deliberately a **single file with no external references**: styles
are inlined, charts are drawn in CSS, and no script or font is fetched. That
means the download opens correctly from a mail attachment, an offline laptop, or
a locked-down corporate machine — and prints to PDF from any browser.
"""
