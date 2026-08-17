"""The Python side of the data quality assistant. The Next app lives in `web/`.

This file is not ceremony: without it mypy maps `app/dq/status.py` to both
`status` and `app.dq.status` and refuses to check anything ("Source file found
twice under different module names"). One empty package marker is a smaller fix
than `--explicit-package-bases` in the gate's configuration.
"""
