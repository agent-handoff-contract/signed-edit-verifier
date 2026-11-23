"""Run the fixed scenarios, check the decisions, and render a static report."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys

from render_report import render_report
from scenarios import run_cases


ROOT = Path(__file__).resolve().parent
WORKFLOW = ".github/workflows/verify-handoff.yml"
CASES = {
    "approve": ("ACCEPTED", None),
    "missing-approval": ("MISSING_APPROVAL", "approval"),
    "stale-revision": ("STALE_REVISION", "revision"),
    "wrong-scope": ("SCOPE_MISMATCH", "scope"),
    "wrong-edit": ("EDIT_MISMATCH", "edit"),
    "tampered-approval": ("INVALID_SIGNATURE", "signature"),
    "already-consumed": ("ALREADY_CONSUMED", "unused"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(cases):
    require(len(cases) == len(CASES) and {r["case_id"] for r in cases} == CASES.keys(),
            "Expected all seven distinct handoff scenarios")
    for receipt in cases:
        case = receipt["case_id"]
        code, failed_check = CASES[case]
        decision = "reject" if failed_check else "accept"
        require(receipt["code"] == receipt["expected_code"] == code, f"{case}: unexpected code")
        require(receipt["decision"] == receipt["expected_decision"] == decision,
                f"{case}: unexpected decision")
        checks = receipt["checks"]
        failed = [key for key, result in checks.items() if result["passed"] is False]
        require(failed == ([failed_check] if failed_check else []), f"{case}: wrong failing check")
        raw = json.dumps(receipt["packet"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        require(hashlib.sha256(raw.encode()).hexdigest() == receipt["packet_sha256"],
                f"{case}: packet digest differs")
        if failed_check:
            require("review_patch" not in receipt, f"{case}: rejected patch emitted")
        else:
            require(receipt["review_patch"] == receipt["packet"]["patch"], "Accepted patch differs")
            require(receipt["observed_blob_sha"] == receipt["expected_blob_sha"],
                    "Accepted file differs from approved file")
        if case == "wrong-edit":
            require(all(checks[k]["passed"] for k in ("revision", "scope", "signature", "patch")),
                    "Wrong-edit case must pass revision, scope, signature and patch application")
            expected, observed = receipt["expected_blob_sha"], receipt["observed_blob_sha"]
            require(expected and observed and expected != observed, "Expected distinct file hashes")
            require(checks["edit"]["expected"] == expected and checks["edit"]["observed"] == observed,
                    "Wrong-edit receipt does not explain its file comparison")


def source_files():
    files = [ROOT / name for name in
             ("receiver.py", "scenarios.py", "demo.py", "render_report.py", WORKFLOW)]
    for directory in ("fixtures", "schemas"):
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file())
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)


def provenance():
    files = source_files()
    hashes = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in files}
    manifest = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    source_id = hashlib.sha256(manifest).hexdigest()
    commit = None
    # Attribute these bytes to a commit only when every source matches its Git blob.
    top = git("rev-parse", "--show-toplevel")
    if top.returncode == 0 and Path(os.fsdecode(top.stdout.strip())).resolve() == ROOT:
        head = git("rev-parse", "--verify", "HEAD^{commit}")
        if head.returncode == 0:
            candidate = head.stdout.decode().strip()
            if all(git("show", f"{candidate}:{name}").stdout == (ROOT / name).read_bytes()
                   for name in hashes):
                commit = candidate

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = {"execution": "Local run", "generated_at": now, "run_id": None, "run_url": None,
              "workflow_commit": None, "verifier_commit": commit, "verifier_source_sha256": source_id,
              "source_files_sha256": hashes}
    if os.environ.get("GITHUB_ACTIONS") == "true":
        run_id = os.environ["GITHUB_RUN_ID"]
        attempt = os.environ["GITHUB_RUN_ATTEMPT"]
        repo = os.environ["GITHUB_REPOSITORY"]
        workflow_commit = os.environ["GITHUB_WORKFLOW_SHA"]
        require(commit is not None and commit == os.environ["GITHUB_SHA"],
                "CI source differs from the event commit")
        require(re.fullmatch(r"[0-9a-f]{40}", workflow_commit) and workflow_commit == commit,
                "Expected the workflow from the same commit for push or manual dispatch")
        result.update(execution="GitHub Actions", run_id=run_id, run_attempt=attempt,
                      run_url=f"https://github.com/{repo}/actions/runs/{run_id}/attempts/{attempt}",
                      workflow_commit=workflow_commit)
    return result


def main():
    origin = provenance()
    cases = run_cases()
    validate(cases)
    for case in cases:
        case["verifier_commit"] = origin["verifier_commit"]
        case["verifier_source_sha256"] = origin["verifier_source_sha256"]
    report = {"schema_version": 1, "provenance": origin, "cases": cases}
    data = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    html = render_report(json.loads(data)).encode()
    target = ROOT / "evidence"
    target.mkdir(exist_ok=True)
    (target / "receipts.json").write_bytes(data)
    (target / "index.html").write_bytes(html)
    for case in cases:
        print(f"{case['case_id']:20} {case['code']}")
    print(f"Receipts SHA-256: {hashlib.sha256(data).hexdigest()}")
    print(f"Report: {target / 'index.html'}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Verification failed: {exc}")
