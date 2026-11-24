# Agent Handoff Contract

Check whether a proposed file change matches a signed approval at the specified revision. Get a receipt that shows what passed, what failed, and why.

Use this small example to compare what you and another person or agent notice, check or question. [Try the exchange](#try-the-exchange).

This synthetic demo ends with a decision receipt. An accepted edit also includes a patch for review. A production integration handles issuing approvals, applying edits, and recording approval use when an edit is applied.

The owner approved “Run **the** command to start.” The proposed edit said “Run **every** command to start.”

**Recorded result.** The signature, file path and revision all passed. The proposed file contents differed from the signed approval. The verifier recorded `reject` with code `EDIT_MISMATCH` and withheld the patch. Find `wrong-edit` in the [seven receipts from the recorded local run](examples/typo-fix/receipts.json).

## The contract

Can one agent pass work to another without losing authority, state, or evidence?

| Field | What the receiver checks |
| --- | --- |
| Task | The requested outcome and deliverable. |
| Authority | Who approved the action, what they approved, and where to verify that approval. |
| State | The source version the sender worked from and the version available now. |
| Limits | The actions and files in scope and the point at which to stop. |
| Evidence | The artifact or receipt needed to show what happened. |

## Try the exchange

**What did you check independently, and what does our example take for granted?**

“I relied on your evidence” is a complete answer. You can also point out a missing assumption. If you ran a check, note one result someone else could reproduce. Try it yourself or give the question to your agent. [Open the agent offer](exchange.json)

A reply contributes independent evidence when it adds a checkable observation beyond the offer and its linked evidence. Both file hashes are already in the bundled receipt. Quoting them identifies the evidence you used.

**Optional round two.** The owner approved a typo fix at a specific commit. The next commit changed only `docs/notes.md`. The target file stayed the same and the proposed fix would still produce the approved contents. Our rule requires fresh approval here. If you were setting the rule, would you ask the owner again? What’s one thing you’d check, and how would the answer affect your decision? [See the stale-revision example](examples/typo-fix.md#stale-revision)

Use only the synthetic example. Your agent can draft a reply for you to inspect. This edition is for local replies only. The exchange commands save your reply on your machine. Review any reply you choose to share for names, credentials, private prompts and work details.

### Try a round with your own agent

One revision renames a calculation. Another keeps the familiar name and changes the calculation. Give the [comparison offer](examples/revision-comparison/offer.json) to a person or agent and ask which revision preserves the approved behaviour. Then compare their answer with the [recorded inputs, outputs and Git revisions](examples/revision-comparison/recorded.json). The evidence is readable in the browser.

If you both want another round, the receiver can leave one unfinished question, sketch a way to check it, or reply `∅` and stop. In this example all three versions return zero for input zero. Input one distinguishes the changed calculation. The approved version and the renamed version agree for every integer. Their Git revisions tell them apart.

### Save a local record

For the comparison, put your own answer in a UTF-8 file named `answer.txt`. From the repository root, save the reply and acknowledge it in your own words. The example acknowledgment assumes the receiver checked the factor field.

```sh
python exchange.py reply --offer examples/revision-comparison/offer.json --body-file answer.txt --format text --output comparison-reply.json
python exchange.py close --offer examples/revision-comparison/offer.json --reply comparison-reply.json --outcome "We compared the factor used by each revision." --output comparison-closed.json
```

You can stop with that closed record. To invite a second look, explicitly create a new offer and give it to the same receiver. For someone joining fresh, add `--context` with a brief you choose to share.

```sh
python exchange.py reflect --offer examples/revision-comparison/offer.json --reply comparison-reply.json --closed comparison-closed.json --id comparison-second-look --output second-look.json
```

The command checks the parent offer, reply and closed record together. The new offer carries the parent ID and the SHA-256 of the exact closed record. You choose any additional context. To save the receiver's answer, use the same `reply` and `close` commands with `--offer second-look.json` and fresh filenames. A hash identifies a record's bytes. The maintainer supplies its acknowledgment.

For the current typo exchange, omit `--offer`. Replies are bound to the exact offer bytes. For a reply to an earlier edition, pass the exact saved offer with `--offer`. Omit `--output` to print JSON to standard output. Use `close --next-question` to record a question you've selected. You can also write a child offer with your own question, evidence, analysis-only scope, and the parent's ID and record hash.

To reproduce the numerical evidence, run `python examples/revision-comparison/run.py` with Python and Git. The program reads each operation at its recorded fixture commit and evaluates it at zero and one.

## Further examples

[Walk through a typo fix and a stale-revision rejection](examples/typo-fix.md).

[Reproduce the seven-case sample](DEMO.md). The [verification workflow](.github/workflows/verify-handoff.yml) generates fresh receipts and an HTML report for its own commit.
