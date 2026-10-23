"""dc-autonomy-v1 Execution agreement contract: section detection plus structural shape.

This file is the canonical copy, beside the runtime loader (agreement.py). The PM
plugin bundles an exact byte copy at pm/scripts/agreement_contract.py so the installed
plugin never depends on an absolute library path; dc-dev-plugins/scripts/
sync_execution_contract.py exports that copy and `--check`s byte parity. Edit here,
re-export, and run both consumers' tests — never hand-edit the bundled copy.

Pure stdlib on purpose (json + re only): both consumers import it as a sibling module.

Two deliberately separate validation layers:

- validate_shape: the full structural contract — policy, approved as a real boolean
  (drafts with approved=false are complete agreements, not excused ones), nonempty
  scope, actions drawn only from ACTIONS, explicit technical_choices, exact build
  bounds, optional frontend/test/review fields validated when present. Generic
  consumers (PM ship acceptance) stop here, so review-only or local-only action
  lists validate.
- validate_runtime: shape plus what the build runtime itself needs — approved must
  be true and actions must include local-edit, local-test, local-commit, ringer-build.

Section detection fails closed: an attempted agreement heading — wrong case, wrong
level, decorated, duplicated, or otherwise ambiguous — raises instead of selecting
legacy behavior. Only genuine absence (no heading starting with the section label)
returns None. The exact section body must be exactly one ```json fence plus
whitespace; the PM intent template already conforms.
"""
import json
import re

POLICY = 'dc-autonomy-v1'
ACTIONS = {'local-edit', 'local-test', 'local-commit', 'ringer-review', 'ringer-build'}
REQUIRED = {'local-edit', 'local-test', 'local-commit', 'ringer-build'}
AGREEMENT_HEADING = 'Execution agreement'

_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def decode(text):
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'invalid JSON number: {value}')))


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in [{low}, {high}]')


def strings(value, name):
    if not isinstance(value, list) or any(not isinstance(s, str) or not s.strip() for s in value) or len(set(value)) != len(value):
        raise ValueError(f'{name} must be an explicit list of unique nonempty strings')


def validate_shape(p):
    """Full structural contract; approved may be true or false but must be a real boolean."""
    required = {'policy', 'approved', 'scope', 'actions', 'technical_choices', 'build'}
    allowed = required | {'frontend_checkpoints', 'test_targets', 'review'}
    if not isinstance(p, dict) or required - p.keys() or p.keys() - allowed:
        raise ValueError('Execution agreement has missing or unknown fields')
    if p['policy'] != POLICY:
        raise ValueError('Execution agreement must use dc-autonomy-v1')
    if type(p['approved']) is not bool:
        raise ValueError('approved must be an actual boolean recording authorization')
    if not isinstance(p['scope'], str) or not p['scope'].strip():
        raise ValueError('scope must be nonempty')
    for key in ('actions', 'technical_choices', 'frontend_checkpoints', 'test_targets'):
        if key in p:
            strings(p[key], key)
    if set(p['actions']) - ACTIONS:
        raise ValueError('unknown actions forbidden; allowed: ' + ', '.join(sorted(ACTIONS)))
    b = p['build']
    if not isinstance(b, dict) or set(b) != {'max_worker_attempts', 'recovery_cycles', 'max_tasks'}:
        raise ValueError('build must contain exactly max_worker_attempts, recovery_cycles, max_tasks')
    for k, low, high in [('max_worker_attempts', 1, 4), ('recovery_cycles', 0, 1), ('max_tasks', 1, 3)]:
        integer(b[k], low, high, k)
    if 'review' in p:
        r = p['review']
        if not isinstance(r, dict) or r.keys() - {'seats', 'max_rounds', 'independent_confirmation'}:
            raise ValueError('unknown review policy')
        if 'seats' in r:
            strings(r['seats'], 'review.seats')
        if 'max_rounds' in r:
            integer(r['max_rounds'], 1, 10, 'review.max_rounds')
        if 'independent_confirmation' in r and type(r['independent_confirmation']) is not bool:
            raise ValueError('independent_confirmation must be boolean')
    return p


def validate_runtime(p):
    """Shape plus the build runtime's own requirements."""
    validate_shape(p)
    if p['approved'] is not True:
        raise ValueError('Execution agreement must use dc-autonomy-v1 and approved=true from actual authorization')
    if not REQUIRED <= set(p['actions']):
        raise ValueError('runtime requires local-edit, local-test, local-commit, ringer-build; unknown actions forbidden')
    return p


def mask_fences(text):
    """Same length as text; every character inside a fenced code block (and the fence lines
    themselves) becomes a space, newlines kept. CommonMark rules: a fence opens with 3+
    backticks or tildes after 0-3 spaces of indent, and closes only on the same character,
    at least as long, with nothing but whitespace after. An unclosed fence at end of file
    raises — it would hide every later section, which is ambiguity, not absence."""
    out = list(text)
    open_char = ''
    open_len = 0
    open_line = 0
    pos = 0
    for n, line in enumerate(text.splitlines(keepends=True), 1):
        m = _FENCE.match(line)
        blank = False
        if open_char:
            blank = True
            if m and m.group(1)[0] == open_char and len(m.group(1)) >= open_len and not m.group(2).strip():
                open_char = ''
        elif m:
            open_char, open_len, open_line = m.group(1)[0], len(m.group(1)), n
            blank = True
        if blank:
            for i, ch in enumerate(line):
                if ch != '\n':
                    out[pos + i] = ' '
        pos += len(line)
    if open_char:
        raise ValueError(f'unclosed code fence opened at line {open_line}')
    return ''.join(out)


def locate(text, heading):
    """Body of the exact `## <heading>` section, or None when genuinely absent.

    Every heading line (any level 1-6) starting with the section label counts as an
    attempt — including any horizontal-whitespace run between the label's words, so
    a spacing typo cannot demote the section to absence; unless exactly one attempt
    exists and it is exactly `## <heading>`, this raises rather than letting a
    near-miss select legacy behavior."""
    masked = mask_fences(text)
    label = r'[^\S\r\n]+'.join(re.escape(word) for word in heading.split())
    attempts = list(re.finditer(r'^ {0,3}#{1,6}[ \t]*' + label
                                + r'\b[^\n]*$', masked, re.M | re.I))
    if not attempts:
        return None
    exact = [m for m in attempts if m.group().strip() == '## ' + heading]
    if len(attempts) != 1 or len(exact) != 1:
        raise ValueError(f'expected exactly one ## {heading} heading')
    start = exact[0].end()
    end = re.search(r'^#{1,2} ', masked[start:], re.M)
    return text[start:start + end.start()] if end else text[start:]


def agreement_block(text, heading=AGREEMENT_HEADING):
    """The decoded agreement object, or None when the intent has no agreement at all."""
    section = locate(text, heading)
    if section is None:
        return None
    match = re.fullmatch(r'\s*```json\s*\n(.*?)\n```\s*', section, re.S)
    if not match:
        raise ValueError(f'{heading} must contain exactly one JSON block and no ambiguous policy text')
    data = decode(match[1])
    if not isinstance(data, dict):
        raise ValueError(f'{heading} must be a JSON object')
    return data
