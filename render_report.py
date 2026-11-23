"""Render a self-contained, read-only view of a recorded verifier run."""

from html import escape
import json
from urllib.parse import urlsplit


STYLE = """
:root { color-scheme: light; --ink: #192822; --muted: #465951; --line: #c3d0c6; }
* { box-sizing: border-box; }
body { margin: 0; color: var(--ink); background: #f4f6f1; font: 1rem/1.55 system-ui, sans-serif; }
main { max-width: 62rem; margin: 0 auto; padding: 2rem 1rem 4rem; }
h1, h2, h3, p { margin: 0 0 .65rem; }
h1 { font-size: clamp(1.7rem, 5vw, 3.1rem); line-height: 1.12; }
h2 { font-size: clamp(1.25rem, 4vw, 1.7rem); line-height: 1.25; }
code, pre, .terminal { font-family: ui-monospace, Consolas, monospace; }
code { overflow-wrap: anywhere; font-size: .9em; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: .88rem; }
.entry { background: #172820; color: #f0f7ef; padding: clamp(1.25rem, 4vw, 2.5rem); }
.terminal { color: #b3dfb7; margin-bottom: .75rem; }
.entry a { color: #bde9c1; }
section { margin-top: 2rem; }
.spot, details { background: #fff; border: 1px solid var(--line); }
.spot { border-left: 4px solid #49654f; padding: 1.25rem; }
.spot p:last-child { margin: .9rem 0 0; }
details { margin: .5rem 0; }
summary { padding: .8rem 1rem; cursor: pointer; }
summary strong { margin-right: .7rem; }
.body { padding: 0 1rem .75rem; }
a { color: #215b41; text-underline-offset: .18em; }
a:focus-visible, summary:focus-visible { outline: 3px solid #ab7200; outline-offset: 3px; }
.hashes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: .6rem; }
.hashes div { padding: .7rem; background: #f2f6ef; }
dl { margin: .65rem 0; }
dt { font-size: .9rem; font-weight: 650; }
dd { margin: .1rem 0 .55rem; }
table { margin: .7rem 0 1rem; border-collapse: collapse; width: 100%; table-layout: fixed; }
th, td { text-align: left; vertical-align: top; padding: .45rem .35rem; overflow-wrap: anywhere; border-bottom: 1px solid var(--line); }
thead { color: var(--muted); }
@media (max-width: 32rem) { main { padding: .65rem .55rem 2rem; } th, td { font-size: .82rem; } }
@media print { body { background: white; } main { max-width: none; padding: 0; } .entry { color: #15221b; background: white; padding: 0; } .entry a, .terminal { color: #215b41; } }
"""


def _value(value):
    if value is None:
        return "—"
    if isinstance(value, (dict, list, bool)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return escape(str(value))


def _field(label, value):
    return f"<div><dt>{escape(label)}</dt><dd><code>{_value(value)}</code></dd></div>"


def _case_detail(case):
    rows = []
    for name, check in case["checks"].items():
        state = {True: "Passed", False: "Failed"}.get(check["passed"], "Skipped")
        rows.append(
            f'<tr><th scope="row">{_value(name)}</th><td>{state}</td>'
            f'<td><code>{_value(check.get("expected"))}</code></td>'
            f'<td><code>{_value(check.get("observed"))}</code></td></tr>'
        )
    receipts = "".join(
        _field(label, case.get(key))
        for label, key in (
            ("Packet SHA-256", "packet_sha256"),
            ("Approval SHA-256", "approval_sha256"),
            ("Fixture commit", "fixture_commit"),
        )
    )
    table = (
        '<table aria-label="Verification checks"><thead><tr><th scope="col">Check</th>'
        '<th scope="col">Result</th><th scope="col">Expected</th>'
        '<th scope="col">Observed</th></tr></thead><tbody>'
        + "".join(rows) + "</tbody></table>"
    )
    patch = case.get("review_patch")
    patch_html = (
        f"<h3>Patch for review</h3><pre>{_value(patch)}</pre>" if patch
        else "<p>The receiver emitted no review patch.</p>"
    )
    return (
        f'<details><summary><strong>{_value(case["title"])}</strong>'
        f'{_value(case["decision"].upper())} · <code>{_value(case["code"])}</code></summary>'
        f'<div class="body"><p>Expected <code>{_value(case["expected_decision"])}'
        f' / {_value(case["expected_code"])}</code></p>{table}{patch_html}'
        f'<dl>{receipts}</dl></div></details>'
    )


def _edit_case(cases):
    case = next((case for case in cases if case["expected_code"] == "EDIT_MISMATCH"), None)
    if case is None:
        return ""
    checks = case["checks"]
    confirmed = (
        case["decision"] == "reject" and case["code"] == "EDIT_MISMATCH"
        and all(checks.get(key, {}).get("passed") is True for key in ("revision", "scope"))
        and bool(case.get("expected_blob_sha")) and bool(case.get("observed_blob_sha"))
        and case["expected_blob_sha"] != case["observed_blob_sha"]
        and not case.get("review_patch")
    )
    outcome = (
        "The revision and file both matched. The proposed edit produced different contents "
        "from those the approver signed off. The receiver rejected it before issuing a review patch."
        if confirmed else
        "Inspect the recorded decision and file hashes below to see which checks ran."
    )
    hashes = (
        _field("Approved file contents · Git blob ID", case.get("expected_blob_sha"))
        + _field("Proposed file contents · Git blob ID", case.get("observed_blob_sha"))
    )
    approved = next((r for r in cases if r.get("code") == "ACCEPTED"), None)
    words = ""
    if approved is not None and confirmed:
        def new_line(receipt):
            added = [line[1:] for line in receipt["packet"]["patch"].splitlines()
                     if line.startswith("+") and not line.startswith("+++")]
            return added[0] if len(added) == 1 else None

        expected_line, proposed_line = new_line(approved), new_line(case)
        if expected_line and proposed_line:
            words = ('<dl class="hashes">' + _field("The approved wording", expected_line)
                     + _field("What the agent proposed", proposed_line) + '</dl>')
    return (
        '<section class="spot"><h2>What if the right file contains the wrong edit?</h2>'
        f'{words}<p>{outcome}</p><dl class="hashes">{hashes}</dl>'
        f'<p>Recorded decision · <code>{_value(case["code"])}</code></p></section>'
    )


def render_report(report: dict) -> str:
    """Render the same cases and provenance that the sibling receipts.json records."""
    cases = report["cases"]
    provenance = report["provenance"]
    matched = sum(
        case["code"] == case["expected_code"] and case["decision"] == case["expected_decision"]
        for case in cases
    )
    origin = "".join(
        _field(label, provenance.get(key))
        for label, key in (
            ("Execution environment", "execution"),
            ("Run ID", "run_id"),
            ("Recorded at", "generated_at"),
            ("Verifier commit", "verifier_commit"),
            ("Workflow commit", "workflow_commit"),
            ("Verifier source · SHA-256", "verifier_source_sha256"),
        )
    )
    run_url = provenance.get("run_url")
    run_link = ""
    if run_url:
        parsed = urlsplit(run_url)
        if parsed.scheme == "https" and parsed.netloc == "github.com":
            run_link = f'<p><a href="{escape(run_url, quote=True)}">Inspect the GitHub Actions run</a></p>'
    details = "".join(_case_detail(case) for case in cases)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Handoff Contract · Verification report</title><style>{STYLE}</style></head>
<body><main><header class="entry"><p class="terminal">handoff &gt; inspect receipt</p>
<h1>What did the agent have permission to change?</h1>
<p>Agent Handoff Contract checks a proposed edit against a signed approval.
This recorded run uses a synthetic Git project.</p>
<p><strong>{matched} of {len(cases)} cases matched their expected decisions.</strong></p>
<a href="receipts.json">Read the machine-readable receipts (JSON)</a></header>
{_edit_case(cases)}
<section><h2>Inspect a decision</h2>{details}</section>
<section><h2>Run provenance</h2><dl>{origin}</dl>{run_link}</section>
</main></body></html>"""
