# Delivery: <intent title>

Intent: <link>. Accepted snapshot: <link + SHA-256>.
Candidate: <commit or artifact SHA-256>. Implementer: <identity>.
Status: blocked | ready-for-release | shipped | released-with-exceptions.

## Acceptance evidence

| ID and original criterion | Phase | Channel | Revision and target | Result | Evaluator and time | Actual evidence |
|---|---|---|---|---|---|---|
| A1: <verbatim criterion> | local/staging | automated | <identity> | pass/fail/not-run | <who, when> | <output or observation/link> |
| A2: <verbatim criterion> | local/staging | ui | <identity> | pass/fail/not-run | <who, when> | <capture link, independently read> |
| A2: <same criterion> | local/staging | state | <identity> | pass/fail/not-run | <who, when> | <persistence read, non-UI channel> |
| A1: <same criterion> | delivered | automated | <identity> | pass/fail/not-run | <who, when> | <output or observation/link> |

One row per required channel when the intent carries Evidence requirements;
a legacy intent without them uses one row per criterion (channel `—`).

## Delivery and review disposition

<Who applied/handed over what, when, destination; human authorization reference.>
<Every review finding: applied, held, refuted or out of scope, and reason.>

## Exceptions and remaining work

<Unmet checks stay visible. Explicit human exceptions name who, when and why.>
<Partial scope, unavailable checks, and follow-up ticket links.>

## Verification of this record

<JSON companion, helper output; helper checks record consistency, not truth.>
