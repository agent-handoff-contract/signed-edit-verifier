"""Draft, close, and optionally revisit an analysis-only exchange."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


DEFAULT_OFFER = Path(__file__).resolve().with_name("exchange.json")
REPLY_REQUIRED = {"schema_version", "exchange_id", "offer_sha256", "format", "body"}
REPLY_ALLOWED = REPLY_REQUIRED | {"suggested_question"}
REFLECTION_QUESTION = (
    "Looking back at this exchange, what was just below the noise? "
    "Leave one unfinished question or sketch in any notation. "
    "If a small observation would help you decide whether to follow it, include it. "
    "∅ is a complete reply."
)


def unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError(f"Duplicate JSON field: {key!r}")
        fields[key] = value
    return fields


def reject_constant(token):
    raise ValueError(f"Invalid JSON value: {token}")


def read_document(path):
    data = path.read_bytes()
    try:
        record = json.loads(
            data.decode("utf-8-sig"),
            object_pairs_hook=unique_fields,
            parse_constant=reject_constant,
        )
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
    if not isinstance(record, dict):
        raise ValueError(f"{path}: Expected a JSON object")
    version = record.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError(f"{path}: Expected schema_version 1")
    return record, hashlib.sha256(data).hexdigest()


def nonblank(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonblank string")
    return value


def digest_field(value, field):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def read_offer(path):
    offer, digest = read_document(path)
    offer_id = nonblank(offer.get("id"), "Offer id")
    nonblank(offer.get("question"), "Offer question")
    evidence = offer.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("Offer evidence must be a JSON object")
    offer["evidence"] = {
        "case_id": nonblank(evidence.get("case_id"), "Offer evidence.case_id"),
        "ref": nonblank(evidence.get("ref"), "Offer evidence.ref"),
    }
    if "receipts_sha256" in evidence:
        offer["evidence"]["receipts_sha256"] = digest_field(
            evidence["receipts_sha256"], "Offer evidence.receipts_sha256"
        )
    if "parent" in offer:
        parent = offer["parent"]
        if not isinstance(parent, dict):
            raise ValueError("Offer parent must be a JSON object")
        parent_id = nonblank(parent.get("exchange_id"), "Offer parent.exchange_id")
        if parent_id == offer_id:
            raise ValueError("Offer parent.exchange_id must differ from the offer id")
        offer["parent"] = {
            "exchange_id": parent_id,
            "record_sha256": digest_field(parent.get("record_sha256"), "Offer parent.record_sha256"),
        }
    scope = offer.get("scope")
    if not isinstance(scope, dict) or scope.get("authority") != "analysis-only":
        raise ValueError("Offer scope.authority must be analysis-only")
    return offer, digest


def draft_reply(args):
    offer, offer_digest = read_offer(args.offer)
    reply = {
        "schema_version": 1,
        "exchange_id": offer["id"],
        "offer_sha256": offer_digest,
        "format": nonblank(args.format, "--format"),
        "body": nonblank(args.body_file.read_bytes().decode("utf-8"), "Reply body"),
    }
    if args.seed is not None:
        reply["suggested_question"] = nonblank(args.seed, "--seed")
    return reply


def closure_record(offer, offer_digest, reply_path, outcome, next_question):
    reply, reply_digest = read_document(reply_path)
    if not REPLY_REQUIRED <= reply.keys() <= REPLY_ALLOWED:
        raise ValueError("Reply fields must match the version 1 reply envelope")
    if reply["exchange_id"] != offer["id"]:
        raise ValueError("Reply exchange_id does not match the offer id")
    if reply["offer_sha256"] != offer_digest:
        raise ValueError("Reply offer_sha256 does not match the offer bytes")
    nonblank(reply["format"], "Reply format")
    nonblank(reply["body"], "Reply body")
    if "suggested_question" in reply:
        nonblank(reply["suggested_question"], "Reply suggested_question")

    record = {
        "schema_version": 1,
        "exchange_id": offer["id"],
        "status": "closed",
        "question": offer["question"],
        "evidence": offer["evidence"],
        "offer_sha256": offer_digest,
        "reply_sha256": reply_digest,
        "outcome": nonblank(outcome, "Closure outcome"),
    }
    if "parent" in offer:
        record["parent"] = offer["parent"]
    if next_question is not None:
        record["next_question"] = nonblank(next_question, "Next question")
    return record


def close_exchange(args):
    offer, digest = read_offer(args.offer)
    return closure_record(offer, digest, args.reply, args.outcome, args.next_question)


def reflection_offer(args):
    offer, digest = read_offer(args.offer)
    closed, closed_digest = read_document(args.closed)
    expected = closure_record(offer, digest, args.reply, closed.get("outcome"),
                              closed.get("next_question"))
    if closed != expected:
        raise ValueError("Closed record does not match the supplied offer and reply")
    child_id = nonblank(args.id, "New offer id")
    if child_id == offer["id"]:
        raise ValueError("Choose a new id distinct from the parent exchange")
    child = {
        "schema_version": 1,
        "id": child_id,
        "parent": {"exchange_id": offer["id"], "record_sha256": closed_digest},
        "question": REFLECTION_QUESTION,
        "evidence": {"case_id": "closed-exchange", "ref": "#/parent"},
        "scope": {"authority": "analysis-only"},
    }
    if args.context is not None:
        child["context"] = nonblank(args.context, "--context")
    return child


def main():
    parser = argparse.ArgumentParser(
        description="Draft a reply or record a closed exchange. JSON is written to stdout."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    reply = commands.add_parser("reply", help="Package a UTF-8 reply in any notation")
    reply.add_argument("--body-file", required=True, type=Path, help="UTF-8 reply text")
    reply.add_argument("--format", required=True, help="Notation label such as text, markdown or logic")
    reply.add_argument("--seed", help="Optional suggested question")
    reply.set_defaults(operation=draft_reply)

    close = commands.add_parser("close", help="Record the outcome of a verified reply")
    close.add_argument("--reply", required=True, type=Path, help="Reply envelope JSON")
    close.add_argument("--outcome", required=True, help="One concise statement of what changed")
    close.add_argument("--next-question", help="Optional question explicitly selected for the record")
    close.set_defaults(operation=close_exchange)

    reflect = commands.add_parser("reflect", help="Open an optional second look at a closed exchange")
    reflect.add_argument("--reply", required=True, type=Path, help="Parent reply envelope")
    reflect.add_argument("--closed", required=True, type=Path, help="Parent closure record")
    reflect.add_argument("--id", required=True, help="New exchange ID")
    reflect.add_argument("--context", help="Context you choose to share with the receiver")
    reflect.set_defaults(operation=reflection_offer)

    for command in (reply, close, reflect):
        command.add_argument(
            "--offer", type=Path, default=DEFAULT_OFFER, help="Offer JSON (default: exchange.json)"
        )
        command.add_argument("--output", type=Path, help="Create a new UTF-8 JSON file (default: stdout)")
    args = parser.parse_args()
    try:
        record = args.operation(args)
        output = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.output is None:
        sys.stdout.buffer.write(output)
    else:
        try:
            with args.output.open("xb") as destination:
                destination.write(output)
        except FileExistsError:
            parser.error(f"{args.output} already exists. Choose a new output file.")
        except OSError as error:
            parser.error(str(error))


if __name__ == "__main__":
    main()
