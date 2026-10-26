"""Whether a Mac has room for one more session: memory, CPU and disk, read before each start.

One shell script reads everything (so the same script runs on this Mac or, through a runner's exec, on another),
`parse` turns its output into a reading, and `check` compares a reading with the runner's limits. A failed check
never stops anything running: the loop just doesn't start more on that runner this tick and says why on the ticket.
"""

import re
import subprocess

DEFAULTS = {'per_session_mb': 3072, 'max_load': 0.85, 'min_disk_gb': 5.0, 'min_memory_level': 15}

# sysctl first (one value per line, in this order), then vm_stat, then df for the folder runs live in.
SCRIPT = ('sysctl -n hw.ncpu hw.memsize kern.memorystatus_level vm.loadavg 2>/dev/null; echo "--vm"; vm_stat; '
          'echo "--df"; df -k {path} | tail -1')


def read(path, run=None):
    """A reading on this Mac (or, with `run`, wherever it runs the script). None when it can't be read."""
    from shlex import quote
    script = SCRIPT.format(path=quote(str(path)))
    if run is None:
        try:
            res = subprocess.run(['/bin/sh', '-c', script], capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return None
        out = res.stdout
    else:
        out = run(script)
    try:
        return parse(out)
    except (ValueError, IndexError):
        return None


def parse(out):
    head, rest = out.split('--vm', 1)
    vm, df = rest.split('--df', 1)
    lines = [l.strip() for l in head.strip().splitlines() if l.strip()]
    ncpu, memsize = int(lines[0]), int(lines[1])
    level = int(lines[2]) if len(lines) > 3 else None          # kern.memorystatus_level: % of memory free
    load1 = float(re.findall(r'[\d.]+', lines[-1])[0])           # vm.loadavg: "{ 1.23 1.10 0.98 }"
    page = int(re.search(r'page size of (\d+) bytes', vm).group(1))
    pages = {k.strip().lower(): int(v.strip().rstrip('.')) for k, v in re.findall(r'^Pages ([^:]+):\s+(\d+)\.?$', vm, re.M)}
    avail = sum(pages.get(k, 0) for k in ('free', 'inactive', 'speculative')) * page // (1024 * 1024)
    cols = df.split()
    disk_gb = int(cols[3]) / (1024 * 1024)                       # df -k: 1K blocks; Available is the 4th column
    return {'ncpu': ncpu, 'memory_mb': memsize // (1024 * 1024), 'memory_level': level, 'available_mb': avail,
            'load1': load1, 'disk_free_gb': round(disk_gb, 1)}


def limits(row):
    """The runner's limits from its row, with the defaults for any left unset."""
    keys = row.keys() if hasattr(row, 'keys') else row
    return {k: (row[k] if k in keys and row[k] is not None else v) for k, v in DEFAULTS.items()}


def check(reading, lim):
    """The reasons there's no room for one more session: 'memory', 'cpu', 'disk' (empty: there is room)."""
    if reading is None:
        return []                       # can't read it: don't hold work back on a guess
    why = []
    if reading['available_mb'] < lim['per_session_mb'] or (
            reading.get('memory_level') is not None and reading['memory_level'] < lim['min_memory_level']):
        why.append('memory')
    if reading['load1'] / max(reading['ncpu'], 1) >= lim['max_load']:
        why.append('cpu')
    if reading['disk_free_gb'] < lim['min_disk_gb']:
        why.append('disk')
    return why


def started(reading, lim):
    """The reading as it will be once one more session runs, so one tick never starts more than fits."""
    if reading is None:
        return None
    return {**reading, 'available_mb': reading['available_mb'] - lim['per_session_mb'], 'load1': reading['load1'] + 1}


def suggest_sessions(memory_mb, ncpu):
    """How many sessions a Mac this size can run side by side: half its cores, and 3 GB each after 8 GB for you."""
    return max(1, min(ncpu // 2, (memory_mb // 1024 - 8) // 3))


def summary(reading, lim):
    """'memory ok' or the first thing that's short, for the board."""
    why = check(reading, lim)
    return f'busy ({why[0]})' if why else ('memory ok' if reading else 'not read')
