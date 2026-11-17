#!/usr/bin/env python3
"""Compile the checked-in source in a fork of the local UCM codebase."""
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
binary = Path(os.getenv('UNISON_BIN', ROOT / 'ucm-bin/ucm-bin')).resolve()
codebase = Path(os.getenv('UNISON_CODEBASE', ROOT / 'unison')).resolve()
target = Path(os.getenv('UNISON_OUTPUT', ROOT / 'unison/evolution.uc')).resolve()
with tempfile.TemporaryDirectory(prefix='unison-build-') as task_dir:
    task = Path(task_dir)
    transcript = task / 'compile.md'
    transcript.write_text(f'''```ucm
unisonProject/main> load {ROOT / 'unison/evolution.u'}
unisonProject/main> update
unisonProject/main> compile main {task / 'evolution'}
```
''')
    result = subprocess.run([str(binary), '-c', str(codebase), 'transcript.fork', str(transcript)],
                            capture_output=True, text=True, timeout=120)
    compiled = task / 'evolution.uc'
    if result.returncode != 0 or not compiled.is_file():
        print(result.stdout)
        print(result.stderr)
        raise SystemExit('Unison compilation failed; previous executable was preserved')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Write beside the destination before atomically replacing it.
    staging = target.with_suffix('.uc.tmp')
    staging.write_bytes(compiled.read_bytes())
    staging.chmod(0o644)
    staging.replace(target)
    print(f'Compiled {target} ({target.stat().st_size} bytes)')
