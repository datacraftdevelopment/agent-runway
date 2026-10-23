---
name: checkpoint
description: Mid-session re-aim when the direction changed but the session shouldn't break, for example a plan mid-run or a result that changes the design. Use when a consequential result lands, or when the user says "checkpoint", "re-aim", "refresh the state", "update the design before we keep going". NOT the session open (whats-next) and NOT the close (stepping-away).
---

# Checkpoint

Re-aim the session in place. Closing and reopening (`stepping-away`, then
`whats-next`) is the clean alternative when the session is cheap to rebuild;
re-aim in place when it isn't, such as a plan halfway through a run. Done when
the record describes the present, not how we got here.

1. **Name what changed,** in one sentence: which assumption, direction or
   result made the current aim stale. If nothing consequential changed, say so
   and stop.
2. **Append a re-aim; never overwrite the Intent.** The session file keeps its
   Intent as written (stepping-away's drift check needs it). Show a short
   before and after, then append through the binding:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session.py" --root "<bound-root>" reaim --session <bound-path> --id <bound-id> --entry-file <reaim-text-file>
   ```

   One line, such as: *Re-aimed 14:30: the import has to keep the legacy IDs;
   done for this session is now the mapping table; the UI drops out.*
3. **Push the change into the work that hasn't happened.** If the design
   changed, edit the design doc and say what changed. If the plan's remaining
   tasks are wrong, revise them in the plan and record the change as a ruling
   in the ledger. A running nested session working an affected lane gets one
   short message with the change. Name every file you touched.
4. **Archive, don't delete.** A replaced decision that still explains the
   project gets an ADR (status superseded, linked both ways) or a line under
   Tried / Learned / Decided. Keep hard constraints exact; don't let a
   preference harden into a rule, or a rule soften into a preference.

It doesn't open or close the session, doesn't append a diary (detail goes in
the design doc, the plan or the ledger), and doesn't commit on its own.
