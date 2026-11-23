"""Replay the seven handoff decisions against a synthetic, pinned Git history."""

import difflib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures"
APPROVAL_ID = "A-017"
GUIDE = "docs/quickstart.md"
NOTES = "docs/notes.md"


def _git(checkout, *args):
    # The Git objects must be identical even on a machine with a configured
    # signing key, alternate object format, global attributes, or another repo.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_ATTR_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Fixture Builder",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture Builder",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_AUTHOR_DATE="2001-01-01T00:00:00+0000",
        GIT_COMMITTER_DATE="2001-01-01T00:00:00+0000",
    )
    result = subprocess.run(
        [
            "git", "-c", "core.autocrlf=false", "-c", "core.filemode=false",
            "-c", "core.attributesFile=" + os.devnull, *args,
        ],
        cwd=checkout, env=env, capture_output=True, check=True,
    )
    return result.stdout.decode("utf-8").strip()


def _create_checkout(checkout):
    checkout.mkdir()
    _git(checkout, "init", "--quiet", "--object-format=sha1", "--initial-branch=main", "--template=")
    (checkout / "docs").mkdir()
    for path in (GUIDE, NOTES):
        (checkout / path).write_bytes((FIXTURES / Path(path).name).read_bytes())
        (checkout / path).chmod(0o644)
    _git(checkout, "add", "--", GUIDE, NOTES)
    _git(checkout, "commit", "--quiet", "-m", "Pin the synthetic documentation fixture")
    return _git(checkout, "rev-parse", "HEAD")


def _patch(path, before, after):
    lines = difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/" + path, tofile="b/" + path,
    )
    return f"diff --git a/{path} b/{path}\n" + "".join(lines)


def run_cases():
    """Return ordered receipts. Each invocation starts with a fresh checkout."""
    from receiver import verify

    store = FIXTURES / "approval-store"
    trust_file = FIXTURES / "trust.json"
    approval_name = APPROVAL_ID + ".json"
    approval = json.loads((store / approval_name).read_bytes())

    with tempfile.TemporaryDirectory(prefix="handoff-scenarios-") as temp:
        work = Path(temp)
        checkout = work / "checkout"
        revision = _create_checkout(checkout)
        if revision != approval["base_commit"]:
            raise ValueError("Reconstructed Git fixture differs from its pinned revision")

        guide_text = (checkout / GUIDE).read_text(encoding="utf-8")
        fixed = guide_text.replace("comand", "command")
        packet = {
            "schema_version": 1, "approval_id": APPROVAL_ID, "base_commit": revision,
            "path": GUIDE, "patch": _patch(GUIDE, guide_text, fixed),
        }
        receipts = []

        def record(case_id, title, code, request, approvals=store, consumed=frozenset()):
            initial_head = _git(checkout, "rev-parse", "HEAD")
            receipt = verify(request, approvals, trust_file, checkout, consumed)
            if _git(checkout, "rev-parse", "HEAD") != initial_head or _git(checkout, "status", "--porcelain"):
                raise AssertionError(f"Scenario {case_id} altered the fixture checkout or index")
            receipts.append({
                **receipt, "case_id": case_id, "title": title,
                "packet": request,
                "expected_code": code,
                "expected_decision": "accept" if code == "ACCEPTED" else "reject",
            })

        record("approve", "The authorised typo correction", "ACCEPTED", packet)
        record("missing-approval", "The named approval is absent", "MISSING_APPROVAL",
               {**packet, "approval_id": "demo-absent"})

        notes = (checkout / NOTES).read_text(encoding="utf-8")
        record("wrong-scope", "A correction to a different file", "SCOPE_MISMATCH",
               {**packet, "path": NOTES, "patch": _patch(NOTES, notes, notes.replace("reciept", "receipt"))})

        different = guide_text.replace("the comand", "every command")
        record("wrong-edit", "The right file and revision, with a different edit", "EDIT_MISMATCH",
               {**packet, "patch": _patch(GUIDE, guide_text, different)})

        altered_store = work / "altered-approval-store"
        shutil.copytree(store, altered_store)
        altered = {**approval, "expected_blob_sha": "0" * 40}
        (altered_store / approval_name).write_bytes((json.dumps(altered, indent=2) + "\n").encode("utf-8"))
        record("tampered-approval", "A signed approval was changed", "INVALID_SIGNATURE", packet, altered_store)

        record("already-consumed", "The apply gate has already consumed this approval",
               "ALREADY_CONSUMED", packet, consumed=frozenset({APPROVAL_ID}))

        # The packet and signed approval still agree with each other. Only
        # reading HEAD from the actual checkout reveals that they are stale.
        (checkout / NOTES).write_bytes((notes + "\nReview scheduled.\n").encode("utf-8"))
        _git(checkout, "add", "--", NOTES)
        _git(checkout, "commit", "--quiet", "-m", "Advance the synthetic checkout")
        record("stale-revision", "The checkout has moved since approval", "STALE_REVISION", packet)
        return receipts
