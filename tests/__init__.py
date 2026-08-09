import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

WORKSPACE_TEMP_ROOT = Path(tempfile.gettempdir()) / "codex-mission-center-tests"

@contextmanager
def workspace_tempdir(prefix: str = "mission-center-"):
    WORKSPACE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = WORKSPACE_TEMP_ROOT / f"{prefix}{uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=True)
    try:
        yield str(temporary)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
