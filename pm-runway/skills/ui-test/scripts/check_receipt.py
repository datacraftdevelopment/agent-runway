#!/usr/bin/env python3
"""Mechanically validate a runner receipt; exit 0 is NOT a product verdict.

usage: check_receipt.py --truth truth.json [--receipt receipt.json]
"""
import argparse
import json
from pathlib import Path
import shlex
import sys


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r} (assertion/artifact IDs must be unique)")
        result[key] = value
    return result


def load_document(path):
    try:
        value = json.loads(Path(path).read_text(), object_pairs_hook=unique_object)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON must be an object")
    return value


def check_case(truth, document, label):
    case_id = truth.get("case_id")
    if not nonempty_string(case_id):
        raise ValueError("truth.case_id must be a nonempty string for the current case")
    if not nonempty_string(document.get("case_id")) or document["case_id"] != case_id:
        raise ValueError(f"{label}.case_id {document.get('case_id')!r} != truth.case_id {case_id!r}")


def runner_outcome(receipt):
    outcome = receipt.get("execution_outcome")
    if outcome not in ("PASS-OBSERVED", "FAIL", "BLOCKED"):
        raise ValueError("execution_outcome must be PASS-OBSERVED|FAIL|BLOCKED")
    return outcome


def negative_reason(document):
    # Report the supplied reason without asserting that incomplete evidence was validated.
    details = {key: document[key] for key in ("blocker", "reason", "basis", "notes", "runner_disagreements")
               if document.get(key)}
    return json.dumps(details, ensure_ascii=False) if details else "no supporting evidence/reason supplied"


def assertion_values(truth):
    assertions = truth.get("assertions")
    if not isinstance(assertions, dict) or not assertions:
        raise ValueError("truth.assertions must be a nonempty object for PASS")
    values = {}
    for aid, spec in assertions.items():
        if not nonempty_string(aid):
            raise ValueError("assertions must have nonempty IDs")
        expected = spec.get("expected") if isinstance(spec, dict) else spec
        if not isinstance(expected, str):
            raise ValueError(f"assertion {aid!r}: expected must be a literal string")
        values[aid] = expected
    return values


def check_reference(ref, references, label):
    if not nonempty_string(ref) or ref not in references:
        raise ValueError(f"{label}: artifact_ref {ref!r} does not name a receipt artifact")


def validate_artifacts(truth, receipt, receipt_path):
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("receipt.artifacts must be a nonempty list for PASS")
    ids, paths = set(), set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not nonempty_string(artifact.get("path")):
            raise ValueError("each artifact must have a nonempty path")
        path = artifact["path"]
        if path in paths:
            raise ValueError(f"duplicate artifact path {path!r}")
        paths.add(path)
        # Legacy receipts can identify artifacts by path alone.
        if "id" in artifact:
            aid = artifact["id"]
            if not nonempty_string(aid):
                raise ValueError("artifact id must be a nonempty string when supplied")
            if aid in ids:
                raise ValueError(f"duplicate artifact id {aid!r}")
            ids.add(aid)
    for artifact in artifacts:
        if artifact.get("id") in paths and artifact["id"] != artifact["path"]:
            raise ValueError(f"ambiguous artifact id/path {artifact['id']!r}")
    required = truth.get("artifacts_required", [])
    if not isinstance(required, list) or any(not nonempty_string(p) for p in required):
        raise ValueError("truth.artifacts_required must be a list of nonempty paths")
    for path in required:
        if path not in paths:
            raise ValueError(f"required artifact {path!r} not listed in receipt.artifacts")

    try:
        from PIL import Image
    except ImportError as exc:
        requirements = Path(__file__).resolve().parents[3] / "requirements.txt"
        raise ValueError("Pillow is required to decode PNG evidence. Install it in the check's Python environment: "
                         f"{shlex.quote(sys.executable)} -m pip install -r {shlex.quote(str(requirements))}") from exc
    for path in paths:
        # Path joins preserve absolute paths and anchor relative paths at the receipt.
        resolved = Path(receipt_path).resolve().parent / path
        try:
            with Image.open(resolved) as image:
                if image.format != "PNG":
                    raise ValueError("image format is not PNG")
                image.verify()  # Check structure and chunk checksums.
            with Image.open(resolved) as image:
                image.load()  # Decode pixels too; a plausible header is insufficient.
        except Exception as exc:
            raise ValueError(f"artifact {resolved}: not a readable decodable PNG: {exc}") from exc
    return ids | paths


def validate_receipt(truth, receipt, receipt_path):
    """Shared PASS gate for both CLIs. Raises ValueError with the failed contract."""
    check_case(truth, receipt, "receipt")
    outcome = runner_outcome(receipt)
    if outcome != "PASS-OBSERVED":
        raise ValueError(f"runner reported {outcome}; product PASS is impossible; {negative_reason(receipt)}")
    expected = assertion_values(truth)
    if not nonempty_string(receipt.get("tool_used")):
        raise ValueError("receipt missing tool_used")
    if receipt.get("read_method") not in ("accessibility", "pixels", "mixed"):
        raise ValueError("read_method must be accessibility|pixels|mixed")
    references = validate_artifacts(truth, receipt, receipt_path)
    for field, ref_key in (("preconditions", "evidence_ref"), ("unexpected", "artifact_ref")):
        entries = receipt.get(field, [])
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError(f"receipt.{field} must be a list of objects")
        for entry in entries:
            if ref_key in entry:
                check_reference(entry[ref_key], references, f"{field}.{ref_key}")
    observations = receipt.get("observations")
    if not isinstance(observations, dict):
        raise ValueError("observations must be an object")
    for aid, observation in observations.items():
        if isinstance(observation, dict):
            if observation.get("source") not in ("accessibility", "pixels"):
                raise ValueError(f"assertion {aid!r}: source must be accessibility|pixels")
            if "artifact_ref" in observation:
                check_reference(observation["artifact_ref"], references, f"assertion {aid!r}")
    for aid, want in expected.items():
        if aid not in observations:
            raise ValueError(f"assertion {aid!r} has no observation")
        observation = observations[aid]
        got = observation.get("raw_text") if isinstance(observation, dict) else observation
        if not isinstance(got, str) or got != want:
            raise ValueError(f"assertion {aid!r}: runner read {got!r}, truth expects {want!r} (literal comparison)")
    mutations = receipt.get("mutations_made")
    if truth.get("mutations_allowed") is False and mutations not in (False, None, [], "false", "none"):
        raise ValueError(f"receipt reports mutations {mutations!r} but the case forbids them")
    return expected, references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", required=True)
    parser.add_argument("--receipt", default="receipt.json")
    args = parser.parse_args()
    try:
        truth = load_document(args.truth)
        receipt = load_document(args.receipt)
        check_case(truth, receipt, "receipt")
        outcome = runner_outcome(receipt)
        if outcome in ("FAIL", "BLOCKED"):
            print(f"NON-PASS — runner reported {outcome}: {negative_reason(receipt)}")
            print("Evidence may be incomplete; no product PASS or evidence-integrity claim. Reset before rerun.")
            return 1
        expected, _ = validate_receipt(truth, receipt, args.receipt)
    except ValueError as exc:
        print(f"FAIL — receipt contract violations: {exc}")
        return 1
    print(f"PASS — mechanical receipt validation: {len(receipt['artifacts'])} PNG(s) decoded; "
          f"{len(expected)} literal reads match truth.")
    print("Runner check success is not a product verdict; capture authenticity is not established.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
