"""Filesystem path helpers that stay correct across run layouts.

The offline (memory/local) backends read bundled sample data. Depending on how
the app is launched, the repository root sits at a different depth relative to
this file:

  - local dev / tests:  <repo>/backend/app/core/paths.py   -> repo is 3 levels up
  - Docker image:       /app/app/core/paths.py             -> code at /app/app,
                        data copied to /app/pipeline/sample_data (2 levels up)

Rather than hard-code a depth, we walk up the ancestor chain and return the first
`pipeline/sample_data/<filename>` that exists. Callers treat a `None` result as
"no sample data available" and degrade gracefully (empty store).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def find_sample_data(filename: str) -> Optional[Path]:
    """Return the path to ``pipeline/sample_data/<filename>`` if it can be found.

    Searches this file's directory and every ancestor. Returns ``None`` when the
    file is absent so the caller can degrade gracefully instead of raising.
    """
    here = Path(__file__).resolve()
    for ancestor in (here.parent, *here.parents):
        candidate = ancestor / "pipeline" / "sample_data" / filename
        if candidate.exists():
            return candidate
    return None
