#!/usr/bin/env python3
"""Validate an acceptance evidence record, not the truth of its evidence.

The evaluator runs checks; this helper catches missing, conflicting, or
self-reported entries. It neither deploys nor marks an intent complete.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agreement_contract as contract  # bundled exact copy of the canonical build-swarm module

EVIDENCE_CHANNELS = ('automated', 'ui', 'state', 'human')

strict_json = contract.decode


def fenced_json(text, heading):
    """The one strict fenced JSON object under the exact `## <heading>`; None only
    when the heading is genuinely absent — a near-miss heading (wrong case, wrong
    level, decorated, duplicate) raises instead of silently dropping the section."""
    section = contract.locate(text, heading)
    if section is None: return None
    blocks = re.findall(r'```(?:json)?\s*\n(.*?)```', section, re.S)
    if len(blocks) != 1: raise ValueError(f'{heading}: expected exactly one fenced JSON block')
    data = strict_json(blocks[0])
    if not isinstance(data, dict): raise ValueError(f'{heading}: not a JSON object')
    return data


def valid_requirements(requirements, criteria):
    """Every acceptance ID maps to a nonempty list of known channels."""
    if not isinstance(requirements, dict) or not requirements: return False
    if set(requirements) != set(criteria): return False
    for cid, channels in requirements.items():
        if cid not in criteria: return False
        if not isinstance(channels, list) or not channels: return False
        if len(channels) != len(set(channels)): return False
        if not all(c in EVIDENCE_CHANNELS for c in channels): return False
    return True


def scalar_identity(value):
    """Identities compare only as nonempty scalar strings; containers, booleans,
    numbers and whitespace-only values are structurally invalid, never 'independent'."""
    return isinstance(value, str) and bool(value.strip())


def channel_verdict(record, check, phase, required):
    """'blocked', or whether a correctly scoped exception was consumed."""
    supplied = check.get('channels', {})
    if not isinstance(supplied, dict): return 'blocked'
    for name, entry in supplied.items():
        # Every supplied channel — declared for this criterion or not — is held to
        # schema and identity. Malformed entries and identity violations are never
        # exceptable, so they block before any exception is consulted.
        if name not in EVIDENCE_CHANNELS or not isinstance(entry, dict): return 'blocked'
        if not all(entry.get(f) for f in ('evaluator', 'evidence', 'at', 'revision')): return 'blocked'
        if not scalar_identity(entry['evaluator']): return 'blocked'
        if entry['evaluator'] == record['implementer']: return 'blocked'
        if entry['revision'] != record['candidate']: return 'blocked'
        if entry.get('status') not in ('pass', 'fail', 'not-run'): return 'blocked'
    exceptions_used = False
    for name in sorted(set(required) | set(supplied)):
        entry = supplied.get(name)
        if entry is not None and entry['status'] == 'pass': continue
        exception = next((e for e in record.get('exceptions', [])
                          if e.get('id') == check['id'] and e.get('phase') == phase
                          and e.get('channel') == name), None)
        if not exception or not all(exception.get(k) for k in ('approved_by', 'reason', 'at')): return 'blocked'
        exceptions_used = True
    return exceptions_used


def verdict(record):
    criteria = record.get('criteria')
    if not isinstance(criteria, dict) or not criteria or not all(criteria.values()): return 'blocked'
    if not record.get('candidate') or not scalar_identity(record.get('implementer')) or not record.get('intent'): return 'blocked'
    requirements = record.get('evidence_requirements')
    if requirements is not None and not valid_requirements(requirements, criteria): return 'blocked'
    exceptions_used = False
    for phase in ('local', 'delivery'):
        data = record.get(phase)
        if phase == 'delivery' and data is None:
            return 'blocked' if exceptions_used else 'ready-for-release'
        if not isinstance(data, dict): return 'blocked'
        if data.get('revision') != record['candidate'] or not data.get('environment'): return 'blocked'
        if phase == 'delivery' and not data.get('applied_by'): return 'blocked'
        checks = data.get('checks', [])
        if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks): return 'blocked'
        ids = [c.get('id') for c in checks]
        if len(ids) != len(set(ids)) or set(ids) != set(criteria): return 'blocked'
        for check in checks:
            if not all(check.get(f) for f in ('evaluator', 'evidence', 'at')): return 'blocked'
            if not scalar_identity(check['evaluator']): return 'blocked'
            if check['evaluator'] == record['implementer']: return 'blocked'
            required = (requirements or {}).get(check['id'])
            if required or 'channels' in check:
                channels = channel_verdict(record, check, phase, required or ())
                if channels == 'blocked': return 'blocked'
                exceptions_used = exceptions_used or channels
            if check.get('status') == 'pass': continue
            if check.get('status') not in ('fail', 'not-run'): return 'blocked'
            exception = next((e for e in record.get('exceptions', [])
                              if e.get('id') == check['id'] and e.get('phase') == phase
                              and e.get('channel') is None), None)
            if not exception or not all(exception.get(k) for k in ('approved_by','reason','at')): return 'blocked'
            exceptions_used = True
    return 'released-with-exceptions' if exceptions_used else 'shipped'


def intent_criteria(text):
    section = re.search(r'^## Acceptance\s*$\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not section: return {}
    result = {}
    entries = re.findall(r'^- \[[ xX]\] (.+)$', section[1], re.M)
    # The supported intent format is a checkbox line per observable criterion.
    for n, entry in enumerate(entries, 1):
        match = re.match(r'(A[0-9]+): (.+)$', entry)
        key, value = (match[1], match[2]) if match else (f'A{n}', entry)
        if key in result: raise ValueError('duplicate acceptance ID in intent')
        result[key] = value
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--record', required=True)
    ap.add_argument('--intent', required=True, help='actual accepted intent file; digest must match the record')
    args = ap.parse_args()
    try:
        record = strict_json(Path(args.record).read_text())
        actual = hashlib.sha256(Path(args.intent).read_bytes()).hexdigest()
        if record.get('intent_sha256') != actual:
            print(json.dumps({'status':'blocked','reason':'intent changed or digest missing'})); return 2
        intent_text = Path(args.intent).read_text()
        expected = intent_criteria(intent_text)
        if not expected or expected != record.get('criteria'):
            print(json.dumps({'status':'blocked','reason':'record criteria differ from accepted intent'})); return 2
        agreement = contract.agreement_block(intent_text)
        requirements = fenced_json(intent_text, 'Evidence requirements')
        if agreement is not None:
            # Unknown or malformed agreements fail closed; they never fall back to legacy
            # handling. The full structural contract applies to drafts too — approved:false
            # never excuses a malformed shape. Unlike the build runtime, this validator
            # accepts approved:false and review-only/local-only action lists.
            contract.validate_shape(agreement)
            if agreement['approved'] and requirements is None:
                print(json.dumps({'status':'blocked','reason':'adopted dc-autonomy-v1 intent lacks an Evidence requirements block'})); return 2
        if requirements is not None and not valid_requirements(requirements, expected):
            print(json.dumps({'status':'blocked','reason':'invalid evidence requirements in accepted intent'})); return 2
        if record.get('evidence_requirements') != requirements:
            print(json.dumps({'status':'blocked','reason':'record evidence requirements differ from accepted intent'})); return 2
        status = verdict(record)
        print(json.dumps({'status':status, 'record':args.record,
                          'verified':'record completeness and revision/identity consistency; not evidence authenticity or deployment'}))
        return 2 if status == 'blocked' else 0
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)})); return 2


if __name__ == '__main__':
    sys.exit(main())
