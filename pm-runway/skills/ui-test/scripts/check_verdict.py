#!/usr/bin/env python3
"""Mechanically validate a product PASS claim against truth and a valid receipt.

Does not establish capture authenticity or independent model transcription.
usage: check_verdict.py --truth truth.json [--receipt receipt.json] [--verdict verdict.json]
"""
import argparse
from pathlib import Path
import sys

from check_receipt import (check_case, check_reference, load_document,
                           negative_reason, nonempty_string, validate_receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", required=True)
    parser.add_argument("--receipt", default="receipt.json")
    parser.add_argument("--verdict", default="verdict.json")
    args = parser.parse_args()
    try:
        truth = load_document(args.truth)
        verdict = load_document(args.verdict)
        check_case(truth, verdict, "verdict")
        outcome = verdict.get("verdict")
        if outcome not in ("PASS", "FAIL", "BLOCKED"):
            raise ValueError("verdict must be PASS|FAIL|BLOCKED")
        if outcome in ("FAIL", "BLOCKED"):
            if Path(args.receipt).exists():
                check_case(truth, load_document(args.receipt), "receipt")
            print(f"NON-PASS — verifier reported {outcome}: {negative_reason(verdict)}")
            print("Evidence may be incomplete; no product PASS or evidence-integrity claim.")
            return 1

        receipt = load_document(args.receipt)
        expected, references = validate_receipt(truth, receipt, args.receipt)
        rows = verdict.get("per_assertion")
        if not isinstance(rows, list) or not rows:
            raise ValueError("per_assertion must be a nonempty list for PASS")
        seen_ids = set()
        for row in rows:
            if not isinstance(row, dict) or not nonempty_string(row.get("id")):
                raise ValueError("each per_assertion row must have a nonempty id")
            aid = row["id"]
            if aid in seen_ids:
                raise ValueError(f"duplicate assertion id {aid!r}")
            seen_ids.add(aid)
            if aid not in expected:
                raise ValueError(f"unknown assertion {aid!r}")
            check_reference(row.get("artifact_ref"), references, f"assertion {aid!r}")
            if row.get("result") != "pass":
                raise ValueError(f"verdict PASS requires assertion {aid!r} result pass")
            observed = row.get("observed_by_verifier")
            if not isinstance(observed, str) or observed != expected[aid]:
                raise ValueError(f"assertion {aid!r}: observed {observed!r} != expected {expected[aid]!r} (literal comparison)")
        missing = expected.keys() - seen_ids
        if missing:
            raise ValueError(f"assertions missing from per_assertion: {sorted(missing)}")
        if not nonempty_string(verdict.get("basis")):
            raise ValueError("verdict.basis missing — state the evidence used")
    except ValueError as exc:
        print(f"FAIL — verdict contract violations: {exc}")
        return 1
    print(f"PASS — mechanical validation of verifier's product PASS: {len(rows)} literal assertion(s), "
          "artifact membership and receipt PNG decoding checked.")
    print("Capture authenticity and independent transcription require review; this check cannot establish them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
