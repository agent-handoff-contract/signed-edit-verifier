# Agent Handoff Contract

A repository owner approved a one-word correction. Can a second agent tell when a proposed patch goes further? Find `wrong-edit` in the [shipped sample](examples/typo-fix/receipts.json) to inspect the signed approval’s expected file hash, the proposed file hash and the receiver’s decision. The sample records a local run from the source files identified in its provenance.

## Reproduce the decisions

From this directory, run `python demo.py` using Python 3.10 or later, Git, and OpenSSH with SSH signature verification. The command builds the synthetic history in a temporary directory, verifies seven handoffs and checks their expected decisions. Open the generated `evidence/index.html` to see the approved and proposed wording side by side, or inspect the inputs and decisions in `evidence/receipts.json`. The fictional `docs-12` and `docs-13` revisions in the [worked example](examples/typo-fix.md) are represented here by real Git commits.

The signed approval fixes the base revision, target path and expected contents of that file. Receiver policy supplies the trusted public key and the paths its holder can approve. The receiver applies a candidate patch to a temporary Git index and compares the resulting file with the approved Git blob. Acceptance returns a patch for the owner to review.

The replay example supplies a ledger snapshot in which the approval was already used. It demonstrates rejection of a known consumed approval. A production service enforcing single use would also need an atomic transaction to consume the approval when applying a change.

## Trace a result

The JSON records each packet, its digest, the supplied approval’s digest where available, the observed fixture revision, and the checks that determined the outcome. To reproduce the shipped sample, compare each case’s packet digest, checks, decision and code. Run timestamps vary. A local source snapshot carries a content digest. A matching Git checkout also records its commit.

The supplied GitHub Actions workflow runs the same command with read-only repository access. Its artifact contains the HTML and JSON. A CI report includes the workflow commit, verifier commit and a link to its specific run attempt. The job log records the receipts file’s SHA-256 for comparison with the downloaded artifact.
