"""pytest bootstrap.

In a normal virtualenv where the project's dependencies (see requirements.txt)
are installed alongside pytest, this file does nothing.

It exists only for sandboxed CI images where the `pytest` launcher runs on a
different interpreter than the one carrying the project's dependencies. In that
case it makes the already-installed system packages importable so the suite can
run without a network install. Paths are appended only if they exist, and only
when `requests` cannot already be imported — so this is a complete no-op in a
proper venv.
"""
import importlib.util
import os
import sys

if importlib.util.find_spec("requests") is None:
    for _p in (
        "/usr/local/lib/python3.11/dist-packages",
        "/usr/lib/python3/dist-packages",
        "/root/.local/lib/python3.11/site-packages",
    ):
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.append(_p)
