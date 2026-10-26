"""runway: the command the app, the skills and a terminal all use. Every rule lives here, once."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import db


def out(obj):
    print(json.dumps(obj, indent=2, sort_keys=True))


# ---- repos and runners -------------------------------------------------------------------------------------------

def git_slug(path):
    """owner/name from the clone's origin URL, or None."""
    res = subprocess.run(['git', '-C', str(path), 'remote', 'get-url', 'origin'], capture_output=True, text=True)
    url = res.stdout.strip()
    if res.returncode != 0 or 'github.com' not in url:
        return None
    tail = url.split('github.com', 1)[1].lstrip(':/')
    return tail[:-4] if tail.endswith('.git') else tail


def base_ref(path, base):
    """origin/<base> after a quick fetch, what Runway builds from; None when the clone has no such branch."""
    subprocess.run(['git', '-C', str(path), 'fetch', '--quiet', 'origin', base], capture_output=True, timeout=60)
    ref = f'origin/{base}'
    ok = subprocess.run(['git', '-C', str(path), 'rev-parse', '--verify', '--quiet', ref], capture_output=True)
    return ref if ok.returncode == 0 else None


def cmd_repo_add(con, a):
    from . import setup
    path = Path(a.path).expanduser().resolve()
    if not (path / '.git').exists():
        raise db.RunwayError(f'{path} is not a git clone')
    slug = git_slug(path)
    if not slug:
        raise db.RunwayError(f'{path} has no GitHub origin; Runway opens and merges pull requests on GitHub')
    name = a.name or path.name
    found = setup.suggest_commands(path, base_ref(path, a.base))
    check = a.check or found['check']
    allow = a.allow if a.allow else found['commands']
    con.execute('INSERT OR REPLACE INTO repos(name, path, slug, base, main_computer, runs_on, check_cmd, worker_commands) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (name, str(path), slug, a.base, a.main, a.runs_on, check,
                                                    json.dumps(allow)))
    db.event(con, 'setup', f'watching {name} ({slug})', repo=name)
    print(f'watching {name}: {path} (base {a.base}, main computer {a.main}, check: {check or "none"}'
          + (f'; sessions may also run: {", ".join(allow)}' if allow else '') + ')')


def cmd_repo_check(con, a):
    """The repo's check command and the other commands Runway's sessions may run, kept in Runway (no commit
    needed). runway.json on the base branch, when it says, still wins. --suggest shows what the clone suggests."""
    from . import setup
    r = db.repo(con, a.name)
    if a.suggest:
        found = setup.suggest_commands(r['path'], base_ref(r['path'], r['base']))
        return out(found) if a.json else print(f'check: {found["check"] or "none found"}\nalso: '
                                               + (', '.join(found['commands']) or 'nothing else'))
    if a.check is not None or a.allow is not None:
        if a.check is not None:
            con.execute('UPDATE repos SET check_cmd=? WHERE name=?', (a.check.strip() or None, a.name))
        if a.allow is not None:
            con.execute('UPDATE repos SET worker_commands=? WHERE name=?',
                        (json.dumps([c for c in a.allow if c.strip()]), a.name))
        db.event(con, 'setup', f'{a.name}: check and session commands set in Runway', repo=a.name)
        r = db.repo(con, a.name)
    allow = json.loads(r['worker_commands'] or '[]')
    if a.json:
        return out({'repo': a.name, 'check': r['check_cmd'], 'commands': allow})
    print(f'{a.name}: check {r["check_cmd"] or "none"}' + (f'; sessions may also run: {", ".join(allow)}' if allow
                                                            else '') + ' (runway.json on the base branch wins)')


def cmd_repo_suggest(con, a):
    from . import setup
    path = Path(a.path).expanduser().resolve()
    found = setup.suggest_commands(path, base_ref(path, 'main'))
    out({'path': str(path), 'name': path.name, 'git': (path / '.git').exists(), 'slug': git_slug(path),
         'check': found['check'], 'commands': found['commands']})


def cmd_repo_list(con, a):
    out([dict(r) for r in con.execute('SELECT * FROM repos ORDER BY name')])


def cmd_repo_archive(con, a):
    from . import tidy
    print(tidy.archive(con, a.name))


def cmd_repo_unarchive(con, a):
    from . import tidy
    print(tidy.unarchive(con, a.name))


def cmd_repo_remove(con, a):
    """Without --yes it only says what would go (and what stays); --json gives the same for the app's confirm."""
    from . import tidy
    r = db.repo(con, a.name)
    n = con.execute('SELECT COUNT(*) FROM tickets WHERE repo=?', (a.name,)).fetchone()[0]
    runs = con.execute('SELECT COUNT(*) FROM runs r JOIN tickets t ON t.id = r.ticket WHERE t.repo=?',
                       (a.name,)).fetchone()[0]
    busy = tidy.running(con, repo=a.name)
    if not a.yes:
        if a.json:
            return out({'repo': a.name, 'path': r['path'], 'tickets': n, 'runs': runs, 'running': busy})
        print(f'runway repo remove {a.name} --yes would delete {n} ticket{"" if n == 1 else "s"} and {runs} '
              f'run{"" if runs == 1 else "s"} (their logs and Runway\'s worktrees), and leave {r["path"]}, its '
              'branches and its pull requests as they are.' + (f' Not now: {", ".join(busy)} running.' if busy else ''))
        return 1
    print(tidy.remove(con, a.name))


def cmd_clear_done(con, a):
    from . import tidy
    if a.undo:
        ids = tidy.unclear(con, a.undo)
        return out(ids) if a.json else print(f'back on the board: {", ".join(ids)}')
    ids = tidy.clear_done(con, a.repo, a.older_than)
    if a.json:
        return out(ids)
    print(f'cleared {len(ids)} done ticket{"" if len(ids) == 1 else "s"} off the board' + (f': {", ".join(ids)}'
          if ids else '') + ('; they still count in stats (undo: runway clear-done --undo ' + ' '.join(ids) + ')'
                             if ids else ''))


def cmd_delete(con, a):
    from . import tidy
    t = db.ticket(con, a.ticket)
    if not a.yes:
        runs = con.execute('SELECT COUNT(*) FROM runs WHERE ticket=?', (a.ticket,)).fetchone()[0]
        busy = tidy.running(con, ticket=a.ticket)
        if a.json:
            return out({'ticket': a.ticket, 'title': t['title'], 'repo': t['repo'], 'runs': runs, 'pr': t['pr'],
                        'branch': t['branch'], 'running': bool(busy)})
        print(f'runway delete {a.ticket} --yes would delete {a.ticket} ({t["title"]}) and its {runs} '
              f'run{"" if runs == 1 else "s"}; its branch' + (f' and PR #{t["pr"]}' if t['pr'] else '') +
              ' stay on GitHub.' + (' Not now: it is running.' if busy else ''))
        return 1
    print(tidy.delete(con, a.ticket))


def cmd_repo_main(con, a):
    db.repo(con, a.name)
    if not con.execute('SELECT 1 FROM runners WHERE name=?', (a.runner,)).fetchone():
        raise db.RunwayError(f'no runner called {a.runner!r}')
    con.execute('UPDATE repos SET main_computer=? WHERE name=?', (a.runner, a.name))
    db.event(con, 'setup', f'{a.name}: main computer is {a.runner}', repo=a.name)
    print(f'{a.name}: main computer is {a.runner}')


def cmd_runner_list(con, a):
    out([dict(r) for r in con.execute('SELECT * FROM runners ORDER BY name')])


def cmd_runner_limits(con, a):
    """A runner's limits for starting one more session: memory per session, CPU load, free disk."""
    from . import capacity
    if not con.execute('SELECT 1 FROM runners WHERE name=?', (a.name,)).fetchone():
        raise db.RunwayError(f'no runner called {a.name!r}')
    for col, val in (('per_session_mb', a.per_session_mb), ('min_cpu_idle_pct', a.min_cpu_idle_pct),
                     ('min_disk_gb', a.min_disk_gb)):
        if val is not None:
            con.execute(f'UPDATE runners SET {col}=? WHERE name=?', (val, a.name))
    row = con.execute('SELECT * FROM runners WHERE name=?', (a.name,)).fetchone()
    lim = capacity.limits(row)
    print(f'{a.name}: up to {row["slots"]} sessions; each needs {lim["per_session_mb"]} MB free, load under '
          f'CPU at least {lim["min_cpu_idle_pct"]:g}% idle, {lim["min_disk_gb"]:g} GB free disk '
          '(the first session only waits for a full disk or critical memory pressure)')


def cmd_runner_set(con, a):
    con.execute('UPDATE runners SET slots=? WHERE name=?', (a.slots, a.name))
    print(f'{a.name}: {a.slots} slots')


def cmd_where(con, a):
    print(db.db_path())


# ---- filing ------------------------------------------------------------------------------------------------------

def cmd_file(con, a):
    """runway file < batch.json, or runway file --repo r ticket.md ... (the person's go is the approval)."""
    from . import tickets
    if a.files:
        if not a.repo:
            raise db.RunwayError('--repo is required with ticket files')
        batch = [tickets.parse_markdown(Path(f).read_text()) for f in a.files]
        for f, t in zip(a.files, batch):
            t.setdefault('key', t.get('id') or Path(f).stem)
        repo, filed_from = a.repo, a.filed_from or 'a terminal'
    else:
        data = json.loads(Path(a.batch).read_text() if a.batch else sys.stdin.read())
        repo = a.repo or data.get('repo')
        if not repo:
            raise db.RunwayError('name the repo: --repo, or "repo" in the JSON')
        batch, filed_from = data.get('tickets', []), a.filed_from or data.get('filed_from') or 'a terminal'
    ids = tickets.file_batch(con, repo, batch, filed_from=filed_from)
    hands = [tid for tid in ids if db.ticket(con, tid)['hands_on']]
    print(f'filed {len(ids)} to {repo}: {", ".join(ids)}')
    if hands:
        print(f'yours to do by hand, Runway never starts {"them" if len(hands) > 1 else "it"}: {", ".join(hands)}'
              f' (the hands-on skill does them in your own session; runway hands-on lists them)')


# ---- status ------------------------------------------------------------------------------------------------------

def cmd_status(con, a):
    from . import status
    if a.prompt:
        if not a.repo:
            raise db.RunwayError('runway status --prompt needs a repo: runway status <repo> --prompt')
        return print(status.repo_prompt(con, a.repo))
    snap = status.snapshot(con)
    if a.json:
        out(snap)
        return
    for r in [r for r in snap['repos'] if not a.repo or r['name'] == a.repo]:
        print(f'{r["name"]}: {r["status_line"]}')
        for t in [t for t in snap['tickets'] if t['repo'] == r['name'] and t['column'] != 'done']:
            where = f' on {t["runs_on"]}' if t['runs_on'] else ''
            print(f'  {t["id"]:6} {t["column"]:9} {t["stage"] or "":7} {t["title"]}{where}')
    for ag in snap['agents']:
        print(f'{ag["kind"]}: ' + (f'resting until {ag["resting_until"]}' if ag['resting_until'] else 'available'))


# ---- take back -----------------------------------------------------------------------------------------------

def cmd_show(con, a):
    from . import take
    print(take.discuss_prompt(con, a.ticket) if a.prompt else take.show(con, a.ticket))


def cmd_take(con, a):
    from . import take
    if a.prompt:
        print(take.prompt(con, a.ticket))       # nothing else: the app copies this
        return
    wt, branch = take.take(con, a.ticket)
    print(f'{a.ticket} is taken back. Its worker is stopped; Runway leaves it alone until you give it back.')
    print(f'worktree: {wt}')
    print(f'branch:   {branch}')
    print()
    print(take.prompt(con, a.ticket))


def cmd_give(con, a):
    from . import take
    head = take.give(con, a.ticket)
    print(f'{a.ticket} is given back at {head[:7]}: it builds again from that commit, then both reviews run on it.')


def cmd_bench(con, a):
    from . import bench
    results = bench.run(con, a.tickets, agents=a.agents.split(','), log=lambda m: print(m, flush=True))
    if a.json:
        out(results)
        return
    print()
    for r in results:
        cost = f'${r["cost_usd"]:.2f}' if r['cost_usd'] is not None else f'{r["tokens"] or 0} tokens'
        print(f'{r["ticket"]:6} {r["agent"]:7} {r["result"]:5} {r["minutes"]:5} min  {cost}'
              + (f'  ({r["why"]})' if r['why'] else ''))
    print('Nothing was pushed; each run\'s record is in ~/.runway/bench/<ticket>/.')


def cmd_retro(con, a):
    """File a retro by hand: for the given reason, or the most frequent one in the last 7 days."""
    from . import retro
    repos = [a.repo] if a.repo else [r['name'] for r in con.execute('SELECT name FROM repos ORDER BY name')]
    since = db.now() - retro.WINDOW_DAYS * 86400
    for repo in repos:
        reason = a.reason
        if not reason:
            row = con.execute("SELECT reason, COUNT(DISTINCT ticket) n FROM stops WHERE repo=? AND at >= ? AND reason "
                              "NOT IN ('not_low_risk', 'taken_back') GROUP BY reason ORDER BY n DESC LIMIT 1",
                              (repo, since)).fetchone()
            if not row:
                print(f'{repo}: nothing stopped in the last {retro.WINDOW_DAYS} days')
                continue
            reason = row['reason']
        tid = retro.file(con, repo, reason, by_hand=True)
        print(f'{repo}: filed {tid}, a retro for "{reason.replace("_", " ")}" (not low risk; it never merges itself)')


def cmd_hands_on(con, a):
    """The tickets that are yours to do, in your own session: Runway never starts one of these."""
    from . import status
    rows = [status.ticket_json(con, t, None) for t in con.execute(
        'SELECT * FROM tickets WHERE state = ? AND cleared_at IS NULL '
        + ('AND repo = ? ' if a.repo else '')
        + 'ORDER BY filed_at, CAST(SUBSTR(id, 3) AS INTEGER)',
        ('hands_on', a.repo) if a.repo else ('hands_on',))]
    if a.json:
        out({'tickets': rows})
        return
    if not rows:
        print('nothing is waiting on you by hand')
        return
    for t in rows:
        waits = f' · waits for {", ".join(t["waits_on"])}' if t['waits_on'] else ''
        blocks = f' · {len(t["blocks"])} Runway ticket{"s" if len(t["blocks"]) != 1 else ""} wait on it' \
            if t['blocks'] else ''
        print(f'{t["id"]:6} {t["repo"]}: {t["title"]}{waits}{blocks}')
    print('runway show <ticket> prints one; runway take <ticket> gives you its worktree; runway done <ticket> on your '
          'go sends it to the code review and the gate (or closes it, when it changed no code).')


def cmd_done(con, a):
    from . import take
    print(take.done(con, a.ticket, a.note, no_code=a.no_code))


def cmd_drop(con, a):
    from . import take
    print(take.drop(con, a.ticket, a.reason))


# ---- stats ---------------------------------------------------------------------------------------------------

def cmd_stats(con, a):
    from . import stats
    snap = stats.snapshot(con, repo=a.repo, days=a.days)
    if a.json:
        out(snap)
        return
    scope = snap['by_repo'][0] if a.repo else snap['all']
    for w in scope['windows']:
        d = w['days']
        rate = f'{w["hands_off_rate"]:.0%}' if w['hands_off_rate'] is not None else 'n/a'
        c = w['cycle_minutes']
        print(f'last {d} days: {w["hands_off"]} of {w["merged"]} merged hands-off ({rate}); '
              f'cycle {c["hands_off"]} min hands-off, {c["rest"]} min the rest'
              + (f'; {w["by_hand"]} done by hand (not counted)' if w['by_hand'] else ''))
        cost = w['cost_per_ticket']
        for v in cost['by_agent']:
            usd = f'${v["median_usd"]}' if v['median_usd'] is not None else 'no dollar cost reported'
            print(f'  {v["agent"]}: {usd}, {v["median_tokens"]} tokens per ticket (median, {v["tickets"]} tickets)')
        if w['stopped']:
            print('  stopped: ' + ', '.join(f'{s["label"]} {s["count"]}' for s in w['stopped']))
    for t in scope['waiting']:
        print(f'waiting for you: {t["id"]} {t["title"]} ({t["label"]})')


# ---- the person's decisions --------------------------------------------------------------------------------------

def cmd_go(con, a):
    from . import actions
    print(actions.answer(con, a.ticket, 'go', a.note))


def cmd_no(con, a):
    from . import actions
    print(actions.answer(con, a.ticket, 'no', a.note))


def cmd_pause(con, a):
    from . import actions
    print(actions.pause(con, a.target, getattr(a, 'for')))


def cmd_resume(con, a):
    from . import actions
    print(actions.resume(con, a.target))


def cmd_start(con, a):
    from . import actions
    if a.ignore_capacity:
        # "Start anyway": this ticket skips the capacity check once (blockers, overlap and slots still apply).
        t = db.ticket(con, a.repo)
        if t['state'] != 'queued':
            raise db.RunwayError(f'{t["id"]} is {t["state"]}; only a ticket waiting in Up next can start anyway')
        con.execute('UPDATE tickets SET ignore_capacity=1 WHERE id=?', (t['id'],))
        db.event(con, 'answer', f'{t["id"]}: start anyway (capacity check skipped once)', repo=t['repo'], ticket=t['id'])
        return print(f'{t["id"]} starts on the next tick, without the capacity check')
    print(actions.start_stop(con, a.repo, True))


def cmd_stop(con, a):
    from . import actions
    print(actions.start_stop(con, a.repo, False))


def cmd_runs_on(con, a):
    from . import actions
    print(actions.runs_on(con, a.target, a.where))


# ---- the loop and setup checks -----------------------------------------------------------------------------------

def cmd_loop(con, a):
    from . import loop
    con.close()
    stamp = lambda m: print(f'{__import__("time").strftime("%H:%M:%S")} {m}', flush=True)
    return loop.run_forever(every=a.every, once=a.once, parent=a.parent_pid, log=stamp)


def cmd_doctor(con, a):
    """Checks this Mac: the tools, and whether Claude Code, Codex and GitHub are signed in. Fills the first-run table."""
    from . import setup
    rep = setup.report(con)
    if a.json:
        out(rep)
        return 0 if rep['ready'] else 1
    def mark(row):
        return 'ok ' if row['ok'] else '-- ' if row['optional'] else 'NO '

    def tail(row):
        if row['ok']:
            return ''
        return '   (optional: one engine is enough)' if row['optional'] else f'   fix: {row["fix"]}'
    for t in rep['tools']:
        print(f'{mark(t)} {t["name"]}{tail(t)}')
    for s in rep['signins']:
        print(f'{mark(s)} {s["label"]} signed in{tail(s)}')
    if not rep['engines']:
        print('NO  an engine: Runway needs Claude Code or Codex (either one), installed and signed in')
    c = rep['command']
    print(f'{"ok " if c["linked"] else "-- "} runway in Terminal' + ('' if c['linked'] else '   fix: runway install-command'))
    sk = rep['skills']
    print(f'{"ok " if sk["installed"] else "-- "} skills: {sk["note"]}')
    return 0 if rep['ready'] else 1


def cmd_init(con, a):
    """Runway's folder and database. First run's "Set it up" runs this; running it again changes nothing. The first
    time, it sizes This Mac's sessions to the Mac: half its cores, 3 GB each after 8 GB for the person."""
    from . import capacity
    print(f'Runway keeps its tickets and runs in {db.db_path()}')
    if db.meta(con, 'sessions_sized') is None:
        r = capacity.read(db.home(), cpu=False)
        if r:
            n = capacity.suggest_sessions(r['memory_mb'], r['ncpu'])
            con.execute("UPDATE runners SET slots=? WHERE name='This Mac'", (n,))
            print(f'This Mac runs up to {n} sessions at once ({r["ncpu"]} cores, {r["memory_mb"] // 1024} GB); '
                  'change it with: runway runner slots "This Mac" <n>')
        db.set_meta(con, 'sessions_sized', 1)


def cmd_install_skills(con, a):
    from . import setup
    agents = [x for x in ('claude', 'codex') if getattr(a, x)] or ['claude', 'codex']
    print(setup.install_skills(agents, update_only=a.update_only))


def cmd_repo_which(con, a):
    """The repo Runway knows the given folder (default: here) by, for file-tickets."""
    res = subprocess.run(['git', '-C', a.path, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if res.returncode != 0:
        raise db.RunwayError(f'{a.path} is not inside a git clone')
    top = str(Path(res.stdout.strip()).resolve())
    slug = git_slug(top)
    for r in con.execute('SELECT name, path, slug FROM repos'):
        if str(Path(r['path']).resolve()) == top or (slug and r['slug'] == slug):
            print(r['name'])
            return 0
    raise db.RunwayError(f'{top} is not watched by Runway; add it with: runway repo add {top}')


def cmd_install_command(con, a):
    from . import setup
    print(setup.install_command(a.to))


# ---- parser ------------------------------------------------------------------------------------------------------

def parser():
    p = argparse.ArgumentParser(prog='runway', description='Runway: tickets run headless, reviewed, merged by a gate.')
    sub = p.add_subparsers(dest='cmd', required=True)

    r = sub.add_parser('repo', help='repos Runway watches').add_subparsers(dest='sub', required=True)
    x = r.add_parser('add', help='watch a local clone')
    x.add_argument('path')
    x.add_argument('--name')
    x.add_argument('--base', default='main')
    x.add_argument('--main', default='This Mac', help='the runner where this clone lives')
    x.add_argument('--runs-on', default='any', choices=['any', 'main'])
    x.add_argument('--check', help="the repo's test command, used when it has no runway.json (default: a guess)")
    x.add_argument('--allow', action='append', help='a command sessions may run (repeat; default: what the clone '
                   'suggests)')
    x.set_defaults(fn=cmd_repo_add)
    x = r.add_parser('check', help="the check and session commands kept in Runway for a repo (show, set or suggest)")
    x.add_argument('name')
    x.add_argument('--check', help='the test command (empty: none)')
    x.add_argument('--allow', action='append', help='a command sessions may run (repeat; replaces the list)')
    x.add_argument('--suggest', action='store_true', help="what the clone's files suggest")
    x.add_argument('--json', action='store_true')
    x.set_defaults(fn=cmd_repo_check)
    x = r.add_parser('which', help='the name Runway knows this clone by')
    x.add_argument('path', nargs='?', default='.')
    x.set_defaults(fn=cmd_repo_which)
    x = r.add_parser('suggest-check', help='what Runway would guess for a clone: name, GitHub slug, check command')
    x.add_argument('path')
    x.set_defaults(fn=cmd_repo_suggest)
    r.add_parser('list').set_defaults(fn=cmd_repo_list)
    x = r.add_parser('main', help="the runner where a repo's clone lives (runs-on main uses it)")
    x.add_argument('name')
    x.add_argument('runner')
    x.set_defaults(fn=cmd_repo_main)
    x = r.add_parser('archive', help='take a repo and its tickets off the board (nothing deleted; unarchive undoes)')
    x.add_argument('name')
    x.set_defaults(fn=cmd_repo_archive)
    x = r.add_parser('unarchive', help='put an archived repo back on the board')
    x.add_argument('name')
    x.set_defaults(fn=cmd_repo_unarchive)
    x = r.add_parser('remove', help="forget a repo: its tickets and run history (never its folder, branches or PRs)")
    x.add_argument('name')
    x.add_argument('--yes', action='store_true', help='really delete (without it: say what would go)')
    x.add_argument('--json', action='store_true', help='without --yes: what would go, for the app')
    x.set_defaults(fn=cmd_repo_remove)

    r = sub.add_parser('runner', help='places tickets run').add_subparsers(dest='sub', required=True)
    r.add_parser('list').set_defaults(fn=cmd_runner_list)
    x = r.add_parser('limits', help='what a runner needs free before it starts another session')
    x.add_argument('name')
    x.add_argument('--per-session-mb', type=int, help='memory each session needs (default 3072)')
    x.add_argument('--min-cpu-idle-pct', type=float, help='CPU idle %% to keep before another session (default 15)')
    x.add_argument('--min-disk-gb', type=float, help='free disk to keep (default 5)')
    x.set_defaults(fn=cmd_runner_limits)
    x = r.add_parser('slots', help='how many tickets a runner takes at once')
    x.add_argument('name')
    x.add_argument('slots', type=int)
    x.set_defaults(fn=cmd_runner_set)

    x = sub.add_parser('file', help='file a batch: JSON on stdin, or Markdown ticket files')
    x.add_argument('files', nargs='*')
    x.add_argument('--repo')
    x.add_argument('--filed-from', help='where the batch came from, e.g. "Claude Code on this Mac"')
    x.add_argument('--batch', help='the JSON batch as a file instead of on stdin')
    x.set_defaults(fn=cmd_file)

    x = sub.add_parser('status', help='what is up next, running, needing you and done')
    x.add_argument('repo', nargs='?', help='only this repo (the board text, or with --prompt)')
    x.add_argument('--json', action='store_true', help='the snapshot the app reads')
    x.add_argument('--prompt', action='store_true', help="a prompt to talk this repo's work over in your agent")
    x.set_defaults(fn=cmd_status)

    for name, fn, text in (('go', cmd_go, 'go on a needs-you ticket'), ('no', cmd_no, 'no on a needs-you ticket')):
        x = sub.add_parser(name, help=text)
        x.add_argument('ticket')
        x.add_argument('--note', help='anything the agent should know (the answer, for "no" on a question)')
        x.set_defaults(fn=fn)
    for name, fn in (('pause', cmd_pause), ('resume', cmd_resume)):
        x = sub.add_parser(name, help=f'{name} everything, one repo or one runner')
        x.add_argument('target', nargs='?')
        if name == 'pause':
            x.add_argument('--for', help='30m, 1h, 2d; default: until you resume')
        x.set_defaults(fn=fn)
    for name, fn in (('start', cmd_start), ('stop', cmd_stop)):
        x = sub.add_parser(name, help=f'{name} picking up new tickets for a repo' + (
            '; or, with --ignore-capacity, start one waiting ticket without the capacity check' if name == 'start' else ''))
        x.add_argument('repo', help='a repo (or a ticket, with --ignore-capacity)')
        if name == 'start':
            x.add_argument('--ignore-capacity', action='store_true', help='this ticket skips the capacity check once')
        else:
            x.set_defaults(ignore_capacity=False)
        x.set_defaults(fn=fn)
    x = sub.add_parser('runs-on', help='where a repo (any|main) or a ticket (any|<runner>) runs')
    x.add_argument('target')
    x.add_argument('where')
    x.set_defaults(fn=cmd_runs_on)

    x = sub.add_parser('loop', help='run the loop (the app starts this; one at a time)')
    x.add_argument('--every', type=int, default=15, help='seconds between ticks')
    x.add_argument('--once', action='store_true', help='one tick, then exit')
    x.add_argument('--parent-pid', type=int, help='stop when this process (the app) goes away')
    x.set_defaults(fn=cmd_loop)
    x = sub.add_parser('doctor', help="check this Mac's tools and sign-ins, with the fix for each")
    x.add_argument('--json', action='store_true', help='what the first-run screen shows')
    x.set_defaults(fn=cmd_doctor)
    x = sub.add_parser('init', help="make Runway's folder and database (~/.runway), if they aren't there yet")
    x.set_defaults(fn=cmd_init)
    x = sub.add_parser('install-skills', help="add Runway's skills to Claude Code and Codex (their plugin commands)")
    x.add_argument('--claude', action='store_true', help='only Claude Code')
    x.add_argument('--codex', action='store_true', help='only Codex')
    x.add_argument('--update-only', action='store_true',
                   help='only update an install that is older than this Runway (the app runs this after an update)')
    x.set_defaults(fn=cmd_install_skills)
    x = sub.add_parser('install-command', help='link runway into ~/.local/bin so Terminal finds it')
    x.add_argument('--to', help='another folder for the link')
    x.set_defaults(fn=cmd_install_command)

    x = sub.add_parser('show', help='a ticket, its Acceptance lines and every run with where its record is')
    x.add_argument('ticket')
    x.add_argument('--prompt', action='store_true', help='a prompt to talk it over in your agent (takes nothing back)')
    x.set_defaults(fn=cmd_show)
    x = sub.add_parser('take', help='take a ticket back: stop its worker, keep its branch, print a prompt')
    x.add_argument('ticket')
    x.add_argument('--prompt', action='store_true', help='print only the prompt, change nothing')
    x.set_defaults(fn=cmd_take)
    x = sub.add_parser('give', help='give a taken-back ticket back: push your commits, queue it again')
    x.add_argument('ticket')
    x.set_defaults(fn=cmd_give)
    x = sub.add_parser('bench', help='head-to-head: re-run done tickets with each engine (never pushes)')
    x.add_argument('tickets', nargs='+')
    x.add_argument('--agents', default='claude,codex')
    x.add_argument('--json', action='store_true')
    x.set_defaults(fn=cmd_bench)
    x = sub.add_parser('retro', help='file a retro ticket now for what keeps stopping tickets')
    x.add_argument('--repo')
    x.add_argument('--reason', help='a stop reason, e.g. check_failed_twice (default: the most frequent)')
    x.set_defaults(fn=cmd_retro)
    x = sub.add_parser('hands-on', help='the tickets that are yours to do by hand; Runway never starts these')
    x.add_argument('--repo')
    x.add_argument('--json', action='store_true')
    x.set_defaults(fn=cmd_hands_on)
    x = sub.add_parser('done', help="finish a ticket yourself: merge its PR, or send a hands-on ticket for review "
                                    "(only on the person's go)")
    x.add_argument('ticket')
    x.add_argument('--note')
    x.add_argument('--no-code', action='store_true', help='a hands-on ticket that changed no code: close it')
    x.set_defaults(fn=cmd_done)
    x = sub.add_parser('drop', help='drop a ticket: close its PR, remove its worktrees')
    x.add_argument('ticket')
    x.add_argument('--reason')
    x.set_defaults(fn=cmd_drop)
    x = sub.add_parser('stats', help='how hands-off it is: merges that needed nothing from you, cycle time, cost')
    x.add_argument('--json', action='store_true', help='what the board strip reads')
    x.add_argument('--repo')
    x.add_argument('--days', type=int, help='one window instead of 7 and 30')
    x.set_defaults(fn=cmd_stats)

    x = sub.add_parser('clear-done', help='take Done tickets off the board (kept for stats and history)')
    x.add_argument('repo', nargs='?')
    x.add_argument('--older-than', help='only those done at least this long ago: 7d, 12h, 30m')
    x.add_argument('--undo', nargs='+', metavar='TICKET', help='put these cleared tickets back on the board')
    x.add_argument('--json', action='store_true', help='the ticket ids, for the app')
    x.set_defaults(fn=cmd_clear_done)
    x = sub.add_parser('delete', help="delete one ticket and its run history (not its branch or PR)")
    x.add_argument('ticket')
    x.add_argument('--yes', action='store_true', help='really delete (without it: say what would go)')
    x.add_argument('--json', action='store_true', help='without --yes: what would go, for the app')
    x.set_defaults(fn=cmd_delete)

    sub.add_parser('where', help='print the database path').set_defaults(fn=cmd_where)
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    # doctor only looks: before first run's "Set it up" (runway init), it checks without making ~/.runway.
    con = db.connect(':memory:') if a.fn is cmd_doctor and not db.db_path().exists() else db.connect()
    try:
        return a.fn(con, a) or 0
    except db.RunwayError as e:
        print(f'runway: {e}', file=sys.stderr)
        return 1
    finally:
        con.close()
