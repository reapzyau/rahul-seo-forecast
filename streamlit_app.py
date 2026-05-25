"""Entry point for Streamlit Cloud — delegates to app.py."""
import os
import runpy

runpy.run_path(
    os.path.join(os.path.dirname(__file__), "app.py"),
    run_name="__main__",
)
