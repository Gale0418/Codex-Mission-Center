import shutil
import sys
import tempfile
import platform as host_platform
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

_SYSTEM_TEMP_ROOT = Path(tempfile.gettempdir())
if sys.platform == "darwin":
    # macOS exposes /var as a symlink to /private/var. Differential fixtures
    # must use the resolved root or Rust correctly rejects them as unsafe.
    _SYSTEM_TEMP_ROOT = _SYSTEM_TEMP_ROOT.resolve()
WORKSPACE_TEMP_ROOT = _SYSTEM_TEMP_ROOT / "codex-mission-center-tests"

_MACH_O_MAGICS = {
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
}

_MACHINE_ALIASES = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "x64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
}
_PE_MACHINES = {"x86_64": 0x8664, "aarch64": 0xAA64}
_ELF_MACHINES = {"x86_64": 62, "aarch64": 183}
_MACH_O_CPUS = {"x86_64": 0x01000007, "aarch64": 0x0100000C}


def _macho_matches_host(stream, header: bytes, expected_cpu: int) -> bool:
    magic = header[:4]
    if magic in {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf"}:
        return int.from_bytes(header[4:8], "big") == expected_cpu
    if magic in {b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"}:
        return int.from_bytes(header[4:8], "little") == expected_cpu
    fat_formats = {
        b"\xca\xfe\xba\xbe": ("big", 20),
        b"\xbe\xba\xfe\xca": ("little", 20),
        b"\xca\xfe\xba\xbf": ("big", 32),
        b"\xbf\xba\xfe\xca": ("little", 32),
    }
    fat_format = fat_formats.get(magic)
    if fat_format is None:
        return False
    byte_order, entry_size = fat_format
    count = int.from_bytes(header[4:8], byte_order)
    if count == 0 or count > 64:
        return False
    stream.seek(8)
    entries = stream.read(count * entry_size)
    return len(entries) == count * entry_size and any(
        int.from_bytes(entries[offset : offset + 4], byte_order) == expected_cpu
        for offset in range(0, len(entries), entry_size)
    )


def native_binary_matches_host(
    path: Path,
    platform: str | None = None,
    machine: str | None = None,
) -> bool:
    """Return whether a candidate's executable format and CPU match the host."""
    platform = platform or sys.platform
    architecture = _MACHINE_ALIASES.get((machine or host_platform.machine()).lower())
    if architecture is None:
        return False
    try:
        with path.open("rb") as stream:
            header = stream.read(64)
            if platform == "win32":
                if len(header) < 64 or header[:2] != b"MZ":
                    return False
                pe_offset = int.from_bytes(header[0x3C:0x40], "little")
                if pe_offset < 64 or pe_offset > 1024 * 1024:
                    return False
                stream.seek(pe_offset)
                coff_header = stream.read(6)
                return (
                    coff_header[:4] == b"PE\0\0"
                    and int.from_bytes(coff_header[4:6], "little")
                    == _PE_MACHINES[architecture]
                )
            if platform.startswith("linux"):
                if header[:6] != b"\x7fELF\x02\x01":
                    return False
                return int.from_bytes(header[18:20], "little") == _ELF_MACHINES[architecture]
            if platform == "darwin":
                return header[:4] in _MACH_O_MAGICS and _macho_matches_host(
                    stream, header, _MACH_O_CPUS[architecture]
                )
    except (OSError, ValueError):
        return False
    return False

@contextmanager
def workspace_tempdir(prefix: str = "mission-center-"):
    WORKSPACE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = WORKSPACE_TEMP_ROOT / f"{prefix}{uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=True)
    try:
        yield str(temporary)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
