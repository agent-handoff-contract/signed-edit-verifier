"""Public CLI checks for an explicitly requested reflection on a closed exchange."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "exchange.py"


class ReflectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        offer = {
            "schema_version": 1,
            "id": "original",
            "question": "PRIVATE-offer?",
            "evidence": {"case_id": "case", "ref": "PRIVATE-evidence"},
            "scope": {"authority": "analysis-only"},
        }
        (self.work / "offer.json").write_text(json.dumps(offer), encoding="utf-8")
        (self.work / "body.txt").write_text("PRIVATE-reply", encoding="utf-8")
        self.reply = ("reply", "--offer", "offer.json", "--format", "text", "--body-file",
                      "body.txt", "--seed", "PRIVATE-seed?")
        self.close = ("close", "--offer", "offer.json", "--reply", "reply.json",
                      "--outcome", "PRIVATE-outcome")
        self.reflect = ("reflect", "--offer", "offer.json", "--reply", "reply.json",
                        "--closed", "closed.json", "--id")
        self.cli(*self.reply, "--output", "reply.json")
        self.cli(*self.close, "--output", "closed.json")

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(CLI), *args], cwd=self.work,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode == 0, ok, result.stderr.decode(errors="replace"))
        return result.stdout

    def document(self, name):
        return json.loads((self.work / name).read_text(encoding="utf-8"))

    def test_explicit_offer_and_empty_set_reply(self):
        self.assertNotIn("next_question", self.document("closed.json"))
        self.assertEqual({p.name for p in self.work.iterdir()},
                         {"offer.json", "body.txt", "reply.json", "closed.json"})
        self.cli(*self.reflect, "child", "--output", "child.json")
        child = self.document("child.json")
        self.assertEqual(child["id"], "child")
        self.assertEqual(child["scope"]["authority"], "analysis-only")
        self.assertIn("∅", child["question"])
        digest = hashlib.sha256((self.work / "closed.json").read_bytes()).hexdigest()
        self.assertEqual(child["parent"]["exchange_id"], "original")
        self.assertEqual(child["parent"]["record_sha256"], digest)
        self.assertNotIn("PRIVATE-", json.dumps(child))
        shared = json.loads(self.cli(*self.reflect, "with-context", "--context", "One public fact"))
        self.assertIn("One public fact", json.dumps(shared))
        self.assertNotIn("PRIVATE-", json.dumps(shared))

        (self.work / "body.txt").write_text("∅", encoding="utf-8")
        reply = self.cli("reply", "--offer", "child.json", "--body-file", "body.txt",
                         "--format", "symbol")
        self.assertEqual(json.loads(reply.decode("utf-8"))["body"], "∅")
        (self.work / "child-reply.json").write_bytes(reply)
        files = set(self.work.iterdir())
        closed = json.loads(self.cli("close", "--offer", "child.json", "--reply",
                                     "child-reply.json", "--outcome", "Leave it here."))
        self.assertEqual(closed["exchange_id"], "child")
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["parent"], child["parent"])
        self.assertNotIn("next_question", closed)
        self.assertEqual(set(self.work.iterdir()), files)

    def test_all_commands_preserve_existing_destination(self):
        occupied = self.work / "existing.json"
        occupied.write_bytes(b"Keep these exact bytes.")
        for args in (self.reply, self.close, (*self.reflect, "child")):
            with self.subTest(command=args[0]):
                self.cli(*args, "--output", occupied.name, ok=False)
                self.assertEqual(occupied.read_bytes(), b"Keep these exact bytes.")

    def test_reflection_requires_matching_documents(self):
        (self.work / "body.txt").write_text("Another valid response", encoding="utf-8")
        self.cli(*self.reply, "--output", "other-reply.json")
        self.cli("close", "--offer", "offer.json", "--reply", "other-reply.json",
                 "--outcome", "A different close", "--output", "other-closed.json")
        for reply, closed in (("other-reply.json", "closed.json"), ("reply.json", "other-closed.json")):
            with self.subTest(reply=reply, closed=closed):
                self.cli("reflect", "--offer", "offer.json", "--reply", reply, "--closed", closed,
                         "--id", "child", "--output", "child.json", ok=False)
                self.assertFalse((self.work / "child.json").exists())

    def test_invalid_closure_and_reused_id(self):
        self.cli(*self.reflect, "original", ok=False)
        closed = self.document("closed.json")
        for field, value in (("status", "open"), ("reply_sha256", "broken"), ("outcome", "")):
            with self.subTest(field=field):
                (self.work / "closed.json").write_text(json.dumps({**closed, field: value}),
                                                       encoding="utf-8")
                self.cli(*self.reflect, "child", ok=False)

    def test_edited_takeaway_changes_the_parent_link(self):
        first = json.loads(self.cli(*self.reflect, "child"))
        closed = self.document("closed.json")
        closed["outcome"] = "A different operator-written takeaway"
        (self.work / "closed.json").write_text(json.dumps(closed), encoding="utf-8")
        second = json.loads(self.cli(*self.reflect, "child"))
        digest = hashlib.sha256((self.work / "closed.json").read_bytes()).hexdigest()
        self.assertEqual(second["parent"]["record_sha256"], digest)
        self.assertNotEqual(first["parent"]["record_sha256"], digest)


if __name__ == "__main__":
    unittest.main()
