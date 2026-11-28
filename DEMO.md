# Agent Handoff Contract

A repository owner approved a one-word correction. Can a second agent tell when a proposed patch goes further? Find `wrong-edit` in the [shipped sample](examples/typo-fix/receipts.json) to inspect the signed approval’s expected file hash, the proposed file hash and the receiver’s decision. The sample records a local run from the source files identified in its provenance.

## Run on GitHub

1. Sign in to GitHub. If you have read-only access to this repository, choose **Fork → Create fork**. Open the **Actions** tab in your fork and enable workflows if prompted. If you already have write access, you can use that repository directly.
2. In **Actions**, select **Verify the worked handoff**. Choose **Run workflow**, select the branch you want to check (usually `main`), then confirm **Run workflow**. The [workflow](.github/workflows/verify-handoff.yml) runs on a GitHub-hosted Ubuntu 24.04 runner with read-only repository permissions.
3. Open your new run and check the commit shown. In the **evidence** job, expand **Verify all scenarios and write the evidence** to see the seven case codes and the SHA-256 of the generated receipts file. The job also checks the optional exchange and a separate revision comparison.
4. To inspect the full results, go back to the run summary. Under **Artifacts**, download `handoff-evidence-<run ID>-<attempt>` and extract it. Open `index.html` for the wording comparison or `receipts.json` for the inputs and decisions. To verify the download, compare the SHA-256 of the extracted `receipts.json` with the value in the job log.

You can also inspect a [completed run](https://github.com/agent-handoff-contract/signed-edit-verifier/actions/runs/45241488729) without starting one. The [sample receipts in the repository](examples/typo-fix/receipts.json) remain available when a run's downloadable artifact expires.

## Run locally

1. Open the GitHub page for the revision you want to check. Use **Code → Download ZIP** and extract it into a fresh, writable folder, or use a Git checkout of that revision. If you prefer a disposable VM, put the writable copy inside the guest. The demo needs only its bundled fixtures and public verification key, so you can leave personal folders and signing keys outside the guest.
2. Open a terminal in the folder containing `demo.py`. You need Python 3.10 or later, Git and OpenSSH's `ssh-keygen` with support for `-Y verify`. Run `python demo.py`, or `python3 demo.py` if that is how you invoke Python 3. There are no Python packages to install.
3. Look for one `ACCEPTED` case and six expected rejections, including `wrong-edit` with `EDIT_MISMATCH`. A successful run exits with status 0 and prints the receipts hash and report path. Open `evidence/index.html` to compare the wording or `evidence/receipts.json` to inspect each decision.

The script creates synthetic Git history in a temporary directory and checks the proposed patches using a temporary Git index. It writes or replaces the two report files under `evidence/` in your copy. The verdict tells you whether the proposed edit matches the signed approval at that revision.

## What the verifier checks

The signed approval fixes the base revision, target path and expected contents of that file. Receiver policy supplies the trusted public key and the paths its holder can approve. The receiver applies a candidate patch to a temporary Git index and compares the resulting file with the approved Git blob. Acceptance returns a patch for the owner to review.

The replay example supplies a ledger snapshot in which the approval was already used. It demonstrates rejection of a known consumed approval. A production service enforcing single use would also need an atomic transaction to consume the approval when applying a change.

## Trace a result

The JSON records each packet, its digest, the supplied approval’s digest where available, the observed fixture revision, and the checks that determined the outcome. To reproduce the shipped sample, compare each case’s packet digest, checks, decision and code. Run timestamps vary. A local source snapshot carries a content digest. A matching Git checkout also records its commit.

A GitHub Actions report also records the workflow commit, verifier commit and a link to that run attempt.
