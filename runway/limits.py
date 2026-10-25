"""Spotting a usage limit in a worker's output, and resting that agent until it resets. From PR #3's journal."""

import re
import time

from . import db

COOLDOWN = 30 * 60  # how long an agent rests after a limit that named no reset time

# What Claude Code and Codex print when a subscription's limit refuses a turn. Phrases, not a bare "rate limit" or
# 429, so a ticket that is about rate limiting does not trip it.
LIMIT_RE = re.compile(r'usage limit (?:reached|exceeded)|limit reached'
                      r'|hit your (?:usage )?limit|usage_limit_reached|usageLimitExceeded|rateLimitExceeded'
                      r'|rate_limit_error|rate limit(?:ed)? (?:reached|exceeded|hit)|out of (?:extra )?usage', re.I)
RESET_RE = re.compile(r'(?:\|(\d{10})\b|resets_?at\W{1,4}(\d{10}))', re.I)


def limit_from(text, now=None):
    """The epoch second an agent can work again, if the text says a usage limit stopped it; else None."""
    if not text or not LIMIT_RE.search(text):
        return None
    now = time.time() if now is None else now
    m = RESET_RE.search(text)
    reset = int(m.group(1) or m.group(2)) if m else 0
    return reset if now < reset < now + 8 * 86400 else int(now + COOLDOWN)


def rest(con, agent, until, why, ticket=None, repo=None):
    con.execute('UPDATE agents SET resting_until=?, reason=? WHERE kind=?', (until, why[:200], agent))
    name = {'claude': 'Claude Code', 'codex': 'Codex'}.get(agent, agent)
    other = 'Codex' if agent == 'claude' else 'Claude Code'
    db.event(con, 'limit', f'{name} hit its usage limit; Any tickets go to {other} until '
             f'{time.strftime("%H:%M", time.localtime(until))}', repo=repo, ticket=ticket)


def available(con, agent):
    row = con.execute('SELECT signed_in, resting_until FROM agents WHERE kind=?', (agent,)).fetchone()
    return bool(row and row['signed_in'] and not (row['resting_until'] and row['resting_until'] > db.now()))
