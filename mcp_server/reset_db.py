"""Reset the working database to the original snapshot.

Copies data/campus_customs.db over data/campus_customs_new.db (the original is only
read, never written) and confirms the two files are byte-identical. Run this before
every full run of the agent team:

    .venv/bin/python mcp_server/reset_db.py
"""

import hashlib
import shutil
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
ORIGINAL = DATA / "campus_customs.db"
WORKING = DATA / "campus_customs_new.db"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reset_database() -> dict:
    if not ORIGINAL.exists():
        raise FileNotFoundError(f"Original database not found: {ORIGINAL}")
    for leftover in (WORKING.with_name(WORKING.name + "-wal"), WORKING.with_name(WORKING.name + "-shm")):
        leftover.unlink(missing_ok=True)
    shutil.copyfile(ORIGINAL, WORKING)
    original_hash, working_hash = _sha256(ORIGINAL), _sha256(WORKING)
    if original_hash != working_hash:
        raise RuntimeError("Reset failed: working copy does not match the original.")
    return {"reset": True, "working_copy": str(WORKING.relative_to(DATA.parent)), "sha256": working_hash}


if __name__ == "__main__":
    print(reset_database())
