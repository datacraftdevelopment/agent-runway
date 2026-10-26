"""Whether a Mac has room for one more session: memory, CPU and disk, read before each start.

One shell script reads everything (so the same script runs on this Mac or, through a runner's exec, on another),
`parse` turns its output into a reading, and `check` compares a reading with the runner's limits. A failed check
never stops anything running: the loop just doesn't start more on that runner this tick and says why on the ticket.

The first session on a runner is held only for a full disk or critical memory pressure: the checks are for extra
sessions. CPU is how busy the processors really are (idle %, sampled over a second, as Activity Monitor shows), not
the load average, which on a Mac counts every thread waiting for anything (Spotlight, the person's own sessions).
"""

import re
import subprocess

DEFAULTS = {'per_session_mb': 3072, 'min_cpu_idle_pct': 15, 'min_disk_gb': 5.0, 'min_memory_level': 15,
            'critical_memory_level': 5}

# sysctl first (one value per line, in this order), then vm_stat, df for the folder runs live in, and top's second
# sample (the first one counts since boot), a second after the first.
SCRIPT = ('sysctl -n hw.ncpu hw.memsize kern.memorystatus_level vm.loadavg 2>/dev/null; echo "--vm"; vm_stat; '
          'echo "--df"; df -k {path} | tail -1; echo "--cpu"; top -l 2 -n 0 -s 1 | grep "CPU usage" | tail -1')


def read(path, run=None, cpu=True):
    """A reading on this Mac (or, with `run`, wherever it runs the script). None when it can't be read. Without
    `cpu` it skips the second-long CPU sample (sizing needs only cores and memory)."""
    from shlex import quote
    script = SCRIPT.format(path=quote(str(path)))
    if not cpu:
        script = script.split('; echo "--cpu"')[0]
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
    except (ValueError, IndexError, AttributeError):
        return None


def parse(out):
    head, rest = out.split('--vm', 1)
    vm, df = rest.split('--df', 1)
    df, _, cpu = df.partition('--cpu')
    lines = [l.strip() for l in head.strip().splitlines() if l.strip()]
    ncpu, memsize = int(lines[0]), int(lines[1])
    level = int(lines[2]) if len(lines) > 3 else None          # kern.memorystatus_level: % of memory free
    load1 = float(re.findall(r'[\d.]+', lines[-1])[0])           # vm.loadavg: "{ 1.23 1.10 0.98 }" (shown, not used)
    page = int(re.search(r'page size of (\d+) bytes', vm).group(1))
    pages = {k.strip().lower(): int(v.strip().rstrip('.')) for k, v in re.findall(r'^Pages ([^:]+):\s+(\d+)\.?$', vm, re.M)}
    avail = sum(pages.get(k, 0) for k in ('free', 'inactive', 'speculative')) * page // (1024 * 1024)
    cols = df.split()
    disk_gb = int(cols[3]) / (1024 * 1024)                       # df -k: 1K blocks; Available is the 4th column
    idle = re.search(r'([\d.]+)% idle', cpu)                      # top: "CPU usage: 39.7% user, 14.9% sys, 45.9% idle"
    return {'ncpu': ncpu, 'memory_mb': memsize // (1024 * 1024), 'memory_level': level, 'available_mb': avail,
            'load1': load1, 'disk_free_gb': round(disk_gb, 1),
            'cpu_idle_pct': round(float(idle.group(1)), 1) if idle else None}


def limits(row):
    """The runner's limits from its row, with the defaults for any left unset."""
    keys = row.keys() if hasattr(row, 'keys') else row
    return {k: (row[k] if k in keys and row[k] is not None else v) for k, v in DEFAULTS.items()}


def gb(mb):
    return f'{mb / 1024:.1f}'.rstrip('0').rstrip('.')


def check(reading, lim, running=1):
    """Why there's no room for one more session, as (what, the reading against its limit); empty: there is room.
    With nothing running on the runner yet (`running` 0), only a full disk or critical memory pressure holds it."""
    if reading is None:
        return []                       # can't read it: don't hold work back on a guess
    why = []
    level = reading.get('memory_level')
    if running == 0:
        if level is not None and level < lim['critical_memory_level']:
            why.append(('memory', f'memory pressure critical ({level}% free)'))
    else:
        if reading['available_mb'] < lim['per_session_mb']:
            why.append(('memory', f'{gb(reading["available_mb"])} GB memory free, a session needs '
                                  f'{gb(lim["per_session_mb"])} GB'))
        elif level is not None and level < lim['min_memory_level']:
            why.append(('memory', f'memory {level}% free, limit {lim["min_memory_level"]}%'))
        idle = reading.get('cpu_idle_pct')
        if idle is not None and idle < lim['min_cpu_idle_pct']:
            why.append(('cpu', f'CPU {100 - idle:.0f}% used, limit {100 - lim["min_cpu_idle_pct"]:.0f}%'))
    if reading['disk_free_gb'] < lim['min_disk_gb']:
        why.append(('disk', f'{reading["disk_free_gb"]:g} GB disk free, limit {lim["min_disk_gb"]:g} GB'))
    return why


def started(reading, lim):
    """The reading as it will be once one more session runs, so one tick never starts more than fits: its memory,
    and about one core of CPU."""
    if reading is None:
        return None
    idle = reading.get('cpu_idle_pct')
    return {**reading, 'available_mb': reading['available_mb'] - lim['per_session_mb'],
            'cpu_idle_pct': None if idle is None else max(0.0, idle - 100 / max(reading['ncpu'], 1))}


def suggest_sessions(memory_mb, ncpu):
    """How many sessions a Mac this size can run side by side: half its cores, and 3 GB each after 8 GB for you."""
    return max(1, min(ncpu // 2, (memory_mb // 1024 - 8) // 3))


def summary(reading, lim=None):
    """'CPU 38% used · 9.2 GB free' for the board, or 'not read'."""
    if not reading:
        return 'not read'
    idle = reading.get('cpu_idle_pct')
    cpu = f'CPU {100 - idle:.0f}% used · ' if idle is not None else ''
    return f'{cpu}{gb(reading["available_mb"])} GB free'
