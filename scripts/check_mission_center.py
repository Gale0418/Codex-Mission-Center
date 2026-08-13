#!/usr/bin/env python3
"""Read-only pre-commit continuity gate for MissionCenter canonical files."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path


def _normalization_required(root: Path) -> bool:
    script=root/'skills/mission-center/scripts/normalize_mission_center.py'
    sys.path.insert(0, str(script.parent))
    from normalize_mission_center import find_header, normalize_labels, normalize_priority, normalize_status
    from common.markdown_table import first_table_block, split_cells
    staged=subprocess.run(
        ['git','-C',str(root),'show',':MissionCenter/tasks.md'],
        capture_output=True,text=True,encoding='utf-8',check=False,
    )
    if staged.returncode != 0: return False
    lines=staged.stdout.splitlines(); block=first_table_block(lines, include_indented=False)
    if len(block)<3: return False
    headers=split_cells(lines[block[0][0]-1]); columns=((find_header(headers,'Priority'),normalize_priority),(find_header(headers,'Status'),normalize_status),(find_header(headers,'Labels'),normalize_labels))
    for _, line in block[2:]:
        cells=split_cells(line)
        if len(cells)!=len(headers): continue
        row=dict(zip(headers,cells))
        if any(header is not None and transform(row[header]) != row[header] for header,transform in columns): return True
    return False


def main() -> int:
    root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
    if _normalization_required(root):
        print('MissionCenter normalization required; run normalize_mission_center.py before committing.', file=sys.stderr); return 1
    # sync and doctor have no check-only CLI. Git validates staged canonical whitespace
    # without executing any writer, preserving the pre-commit gate's read-only contract.
    return subprocess.run(['git','-C',str(root),'diff','--check','--cached','--','MissionCenter']).returncode
if __name__ == '__main__': raise SystemExit(main())
