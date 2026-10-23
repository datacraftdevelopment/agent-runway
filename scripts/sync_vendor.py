#!/usr/bin/env python3
"""Rebuild pm-runway's vendored part from its two upstreams.

pm-runway is pm-sp plus Matt Pocock's ticket flow plus the Runway ticket side.
This script owns the vendored part only:

  * everything pm-sp ships (git-tracked files at the given checkout), with
    every "pm-sp" renamed to "pm-runway", except the files listed in OURS;
  * Matt Pocock's tdd and code-review, verbatim apart from EDITS.

Everything in OURS is pm-runway's own text (some of it derived from Matt's
skills, see VENDOR.md) and is never touched here. Run it, read the diff,
update VENDOR.md's commits, run the tests:

    python3 scripts/sync_vendor.py --pm-sp ../dc-dev-plugins/pm-sp --matt ../mattpocock-skills
    python3 -m unittest discover -s tests
"""
import argparse
import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / 'pm-runway'

# pm-runway's own files, relative to pm-runway/. Never overwritten.
OURS = {
    '.claude-plugin/plugin.json',
    'README.md',
    'VENDOR.md',
    'RUNWAY.md',
    'skills/second-opinion/SKILL.md',
    'template/docs/agents/issue-tracker.md',
}
OURS_DIRS = (
    'runway/',
    'bin/',
    'skills/runway-ask/',
    'skills/to-spec/',
    'skills/to-tickets/',
    'skills/implement-spec/',
    'skills/work-ticket/',
    'skills/review-ticket/',
    'templates/runway/',
)

# Matt's skills copied verbatim (plus EDITS), from skills/engineering/.
MATT_VERBATIM = ('tdd', 'code-review')

# Exact edits to vendored files: (path under pm-runway/, old, new). Each must match once.
EDITS = [
    ('skills/brainstorming/SKILL.md',
     """4. Ask whether to plan it now, and invoke the pm-runway:writing-plans skill
   only when they say go (pm-runway; see the HARD-GATE below).""",
     """4. Ask whether to plan it now, and how: by hand (pm-runway:writing-plans), or as
   tickets for the loop (pm-runway:to-spec, then pm-runway:to-tickets). Invoke
   either only when they say go (pm-runway; see the HARD-GATE below)."""),
    ('skills/brainstorming/SKILL.md',
     """session. When they say go, the next step is the plan: invoke
pm-runway:writing-plans and no other skill.""",
     """session. When they say go, the next step is the plan: invoke
pm-runway:writing-plans, or for work headed to the loop pm-runway:to-spec
(which hands to pm-runway:to-tickets), and no other skill. pm-runway: ticketed
work has no separate plan document; the spec and the tickets are the plan."""),
    ('skills/code-review/SKILL.md',
     'The issue tracker should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`.',
     'The issue tracker is described in `docs/agents/issue-tracker.md` (pm-runway: a chunk\'s spec and tickets are files, '
     '`docs/specs/` and `docs/maps/<effort>/tickets/`).'),
]


def git_files(src: Path, sub: str = '.'):
    """Yield (relative path, bytes) for every git-tracked file under src/sub at HEAD."""
    top = Path(subprocess.run(['git', '-C', str(src), 'rev-parse', '--show-toplevel'],
                              check=True, capture_output=True, text=True).stdout.strip()).resolve()
    prefix = (Path(src).resolve() / sub).relative_to(top).as_posix()
    data = subprocess.run(['git', '-C', str(top), 'archive', '--format=tar', 'HEAD', '--', prefix],
                          check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            if m.issym() or m.islnk():
                sys.exit(f'refusing a link in upstream: {m.name}')
            if m.isfile():
                rel = m.name if prefix == '.' else m.name[len(prefix) + 1:]
                yield rel, tar.extractfile(m).read(), m.mode


def head(src: Path) -> str:
    return subprocess.run(['git', '-C', str(src), 'rev-parse', '--short', 'HEAD'],
                          check=True, capture_output=True, text=True).stdout.strip()


def ours(rel: str) -> bool:
    return rel in OURS or rel.startswith(OURS_DIRS)


def rename(rel: str, data: bytes) -> bytes:
    if rel.endswith(('.png', '.jpg', '.gif', '.ico')):
        return data
    try:
        text = data.decode()
    except UnicodeDecodeError:
        return data
    return text.replace('pm-sp', 'pm-runway').replace('pm_sp', 'pm_runway').encode()


def write(rel: str, data: bytes, mode: int):
    dest = PLUGIN / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    dest.chmod(0o755 if mode & 0o111 else 0o644)


def clear_vendored():
    if not PLUGIN.exists():
        return
    for p in sorted(PLUGIN.rglob('*'), reverse=True):
        rel = p.relative_to(PLUGIN).as_posix()
        if p.is_file() and not ours(rel):
            p.unlink()
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pm-sp', required=True, type=Path, help='the pm-sp folder of a dc-dev-plugins checkout')
    ap.add_argument('--matt', required=True, type=Path, help='a mattpocock/skills checkout')
    args = ap.parse_args()

    clear_vendored()
    skipped = []
    for rel, data, mode in git_files(args.pm_sp):
        if ours(rel):
            skipped.append(rel)
            continue
        write(rel, rename(rel, data), mode)
    for skill in MATT_VERBATIM:
        for rel, data, mode in git_files(args.matt, f'skills/engineering/{skill}'):
            if rel.startswith('agents/'):
                continue  # Codex agent cards, not used
            write(f'skills/{skill}/{rel}', data, mode)
    for rel, old, new in EDITS:
        p = PLUGIN / rel
        text = p.read_text()
        if text.count(old) != 1:
            sys.exit(f'edit no longer matches once in {rel}: {old[:60]!r}')
        p.write_text(text.replace(old, new))

    print(f'pm-sp at {head(args.pm_sp)}, mattpocock/skills at {head(args.matt)}')
    print('kept pm-runway\'s own copy of:', ', '.join(sorted(skipped)) or 'nothing')
    print('Now update the commits in pm-runway/VENDOR.md and run the tests.')


if __name__ == '__main__':
    main()
