# Worked example: a typo fix

This example uses a fictional repository and approval record.

## Incoming handoff

| Field | Value |
| --- | --- |
| Task | Prepare a patch that changes `comand` to `command` in `docs/quickstart.md`. |
| Authority | The repository owner approved this edit in record `A-017`. The receiver can check that record. |
| State | The patch must target revision `docs-12`. The expected line is `Run the comand to start.` |
| Limits | Return a patch for review. The repository owner applies it. |
| Evidence | Return the decision, the observed revision, and either the patch and checks performed or the reason for rejection. |

## Matching revision

The receiver checks `A-017`, confirms the source is `docs-12`, and finds the expected line. It returns `typo.patch` for review.

```diff
--- a/docs/quickstart.md
+++ b/docs/quickstart.md
@@ -1 +1 @@
-Run the comand to start.
+Run the command to start.
```

The receipt records `accept`. The receiver returns the patch for the owner to review after checking that it touches one file and produces the exact contents the owner approved.

## Stale revision

For the same handoff, suppose the receiver observes `docs-13`. In the runnable fixture, only `docs/notes.md` changed. The target file stayed the same and the approved edit would produce the same contents. The approval names the earlier commit, so the receiver records `reject` with code `STALE_REVISION`. The owner can review the new revision and issue a fresh approval.
