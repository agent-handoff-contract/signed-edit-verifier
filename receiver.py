"""Verify one synthetic handoff against a receiver-owned policy and Git fixture."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory


NAMESPACE = "agent-handoff-contract"
OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
APPROVAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
PACKET_FIELDS = {"schema_version", "approval_id", "base_commit", "path", "patch"}
APPROVAL_FIELDS = {
    "schema_version", "approval_id", "approver", "base_commit", "path", "expected_blob_sha"
}


def git(checkout, *args, data=None, env=None, must_succeed=True):
    return subprocess.run(
        ["git", "-C", str(checkout), *args], input=data, capture_output=True,
        env=env, check=must_succeed
    )


def valid_record(record, fields):
    return (
        isinstance(record, dict)
        and set(record) == fields
        and type(record["schema_version"]) is int
        and record["schema_version"] == 1
        and all(isinstance(record[k], str) for k in fields - {"schema_version"})
        and APPROVAL_ID.fullmatch(record["approval_id"]) is not None
        and OID.fullmatch(record["base_commit"]) is not None
    )


def allowed_path(path):
    parts = path.split("/")
    return (
        all(part and part not in {".", ".."} and part.lower() != ".git" for part in parts)
        and not any(c in path for c in "\\:\x00\r\n\t")
    )


def signature_matches(approval_bytes, signature, policy, scratch):
    if not signature.is_file():
        return False
    principal = policy["principal"]
    public_key = policy["public_key"]
    if not re.fullmatch(r"[a-zA-Z0-9_.@-]+", principal):
        raise ValueError("Invalid principal in receiver policy")
    key_parts = public_key.strip().split()
    if len(key_parts) < 2 or key_parts[0] != "ssh-ed25519":
        raise ValueError("Receiver policy needs an Ed25519 public key")
    allowed_signers = scratch / "allowed_signers"
    allowed_signers.write_bytes(f"{principal} {key_parts[0]} {key_parts[1]}\n".encode("ascii"))
    proc = subprocess.run(
        ["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", principal,
         "-n", NAMESPACE, "-s", str(signature)], input=approval_bytes, capture_output=True
    )
    if proc.returncode and b"unknown option" in proc.stderr.lower():
        raise RuntimeError("The installed ssh-keygen must support SSH signatures (-Y verify)")
    return proc.returncode == 0


def patch_paths(checkout, patch, env):
    """List each diff target, including duplicate targets, before applying the patch."""
    stat = git(checkout, "apply", "--numstat", "-z", "-", data=patch, env=env, must_succeed=False)
    if stat.returncode:
        return None
    paths = []
    for entry in stat.stdout.split(b"\0"):
        if entry:
            fields = entry.split(b"\t", 2)
            if len(fields) != 3:
                return None
            paths.append(fields[2].decode("utf-8", errors="replace"))
    return paths


def verify(packet: dict, approval_dir: Path, trust_file: Path, checkout: Path,
           consumed: frozenset[str] = frozenset()) -> dict:
    """Return a receipt. The packet cannot select its approval store, signer or checkout."""
    # A parent process may itself have a different Git checkout/index selected.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1",
               GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
    head = git(checkout, "rev-parse", "--verify", "HEAD^{commit}", env=env).stdout.decode().strip()
    packet_bytes = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    receipt = {
        "schema_version": 1, "decision": "reject", "code": "INVALID_PACKET", "checks": {},
        "expected_blob_sha": None, "observed_blob_sha": None, "fixture_commit": head,
        "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(), "approval_sha256": None
    }

    def record(name, passed, expected, observed, failure):
        receipt["checks"][name] = {"passed": passed, "expected": expected, "observed": observed}
        if not passed:
            receipt["code"] = failure
        return passed

    if not valid_record(packet, PACKET_FIELDS):
        return receipt
    approval_id = packet["approval_id"]
    path = packet["path"]
    if not allowed_path(path):
        record("scope", False, "relative repository file", path, "SCOPE_MISMATCH")
        return receipt
    approval_file = Path(approval_dir) / (approval_id + ".json")
    found = approval_file.is_file()
    if not record("approval", found, approval_id, approval_id if found else None, "MISSING_APPROVAL"):
        return receipt
    approval_bytes = approval_file.read_bytes()
    receipt["approval_sha256"] = hashlib.sha256(approval_bytes).hexdigest()
    policy = json.loads(Path(trust_file).read_bytes())
    if not isinstance(policy["paths"], list) or not all(
        isinstance(path_name, str) and allowed_path(path_name) for path_name in policy["paths"]
    ):
        raise ValueError("Receiver policy must list exact repository file paths")

    with TemporaryDirectory(prefix="handoff-verify-") as temp:
        scratch = Path(temp).resolve()
        sig = approval_file.with_suffix(".json.sig")
        verified = signature_matches(approval_bytes, sig, policy, scratch)
        if not record("signature", verified, policy["principal"],
                      policy["principal"] if verified else None, "INVALID_SIGNATURE"):
            return receipt
        try:
            approval = json.loads(approval_bytes)
        except (ValueError, UnicodeDecodeError):
            approval = None
        valid = (valid_record(approval, APPROVAL_FIELDS)
                 and approval["approval_id"] == approval_id
                 and approval["approver"] == policy["principal"]
                 and OID.fullmatch(approval["expected_blob_sha"]) is not None)
        if not record("approval_record", valid, "valid signed approval for this ID and principal",
                      valid, "INVALID_APPROVAL"):
            return receipt
        expected_sha = approval["expected_blob_sha"]
        receipt["expected_blob_sha"] = expected_sha
        revision_ok = head == packet["base_commit"] == approval["base_commit"]
        if not record("revision", revision_ok, approval["base_commit"],
                      {"checkout": head, "packet": packet["base_commit"]}, "STALE_REVISION"):
            return receipt
        if not record("authority", approval["path"] in policy["paths"], policy["paths"],
                      approval["path"], "SCOPE_MISMATCH"):
            return receipt
        patch = packet["patch"].encode("utf-8")
        targets = patch_paths(checkout, patch, env)
        if targets is None:
            record("patch", False, "valid unified diff", "invalid diff", "INVALID_PATCH")
            return receipt
        scope_ok = approval["path"] == path and targets == [path]
        if not record("scope", scope_ok, approval["path"], {"packet": path, "patch": targets},
                      "SCOPE_MISMATCH"):
            return receipt
        if not record("unused", approval_id not in consumed, "unused",
                      "consumed" if approval_id in consumed else "unused", "ALREADY_CONSUMED"):
            return receipt

        dirty = git(checkout, "status", "--porcelain=v1", "--untracked-files=normal", env=env).stdout
        if not record("clean", not dirty, "clean checkout", "dirty" if dirty else "clean checkout",
                      "DIRTY_CHECKOUT"):
            return receipt
        # Use a private index *and* object directory, so even rejected post-images stay disposable.
        objects = scratch / "objects"
        objects.mkdir()
        base_objects = git(checkout, "rev-parse", "--path-format=absolute", "--git-path", "objects",
                           env=env).stdout.decode().strip()
        index_env = {**env, "GIT_INDEX_FILE": str(scratch / "index"),
                     "GIT_OBJECT_DIRECTORY": str(objects), "GIT_ALTERNATE_OBJECT_DIRECTORIES": base_objects}
        git(checkout, "read-tree", head, env=index_env)
        applied = git(checkout, "apply", "--cached", "--whitespace=nowarn", "-", data=patch,
                      env=index_env, must_succeed=False)
        if not record("patch", applied.returncode == 0, "applies to pinned commit",
                      "applied" if not applied.returncode else "does not apply", "INVALID_PATCH"):
            return receipt
        changes = git(checkout, "diff-index", "--cached", "--raw", "--no-abbrev",
                      "--no-renames", "-z", head, "--", env=index_env).stdout.split(b"\0")
        # An ordinary edit preserves the mode of one existing regular file and changes its blob.
        meta = changes[0].split() if len(changes) == 3 else []
        regular_edit = (len(meta) == 5 and changes[1] == path.encode()
                        and meta[0] in {b":100644", b":100755"}
                        and meta[1] == meta[0][1:] and meta[4] == b"M")
        if not record("file_kind", regular_edit, "one modified regular file, same mode",
                      changes[0].decode(errors="replace") if changes[0] else None, "INVALID_EDIT"):
            return receipt
        observed_sha = meta[3].decode("ascii")
        receipt["observed_blob_sha"] = observed_sha
        if not record("edit", expected_sha == observed_sha, expected_sha, observed_sha,
                      "EDIT_MISMATCH"):
            return receipt
        receipt.update(decision="accept", code="ACCEPTED", review_patch=packet["patch"])
        return receipt
