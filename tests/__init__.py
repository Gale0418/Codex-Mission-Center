import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

_SYSTEM_TEMP_ROOT = Path(tempfile.gettempdir())
if sys.platform == "darwin":
    # macOS exposes /var as a symlink to /private/var. Differential fixtures
    # must use the resolved root or Rust correctly rejects them as unsafe.
    _SYSTEM_TEMP_ROOT = _SYSTEM_TEMP_ROOT.resolve()
WORKSPACE_TEMP_ROOT = _SYSTEM_TEMP_ROOT / "codex-mission-center-tests"

@contextmanager
def workspace_tempdir(prefix: str = "mission-center-"):
    WORKSPACE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = WORKSPACE_TEMP_ROOT / f"{prefix}{uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=True)
    try:
        yield str(temporary)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
