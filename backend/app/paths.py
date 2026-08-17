"""Filesystem anchors, in one place so no module re-derives them.

Kept free of imports and side effects: db.py creates the database directory on
import, and scoring.py must stay usable (from the experiments scripts) without
touching the database at all.
"""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
