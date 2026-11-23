"""Rebuild three synthetic commits and observe their integer multiplication."""

import json
from pathlib import Path
import sys
import tempfile


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from scenarios import _git


def compare():
    example = json.loads((HERE / "offer.json").read_bytes())["example"]
    approved = example["approved_base_commit"]
    inputs = [0, 1]
    expected = {"base": [0, 2], "A": [0, 2], "B": [0, 3]}
    revisions = {}

    with tempfile.TemporaryDirectory(prefix="revision-comparison-") as directory:
        repo = Path(directory)
        _git(repo, "init", "--quiet", "--object-format=sha1", "--initial-branch=base", "--template=")
        path = repo / "operation.json"
        for label, expected_outputs in expected.items():
            if label != "base":
                _git(repo, "checkout", "-q", "-b", label, approved)
            record = example["records"][label]
            data = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            path.write_bytes(data.encode("utf-8"))
            path.chmod(0o644)
            _git(repo, "add", "--", path.name)
            _git(repo, "commit", "-q", "-m", f"Revision {label}")
            commit = _git(repo, "rev-parse", "HEAD")
            parents = _git(repo, "show", "-s", "--format=%P", commit).split()
            if label == "base" and commit != approved:
                raise ValueError("Reconstructed base differs from the approved commit")
            if parents != ([] if label == "base" else [approved]):
                raise ValueError(f"{label}: unexpected commit parents")

            operation = json.loads(_git(repo, "cat-file", "blob", f"{commit}:{path.name}"))
            factor = operation["factor"]
            if type(factor) is not int:
                raise ValueError(f"{label}: expected an integer factor")
            outputs = [value * factor for value in inputs]
            if outputs != expected_outputs:
                raise ValueError(f"{label}: unexpected outputs {outputs}")
            revisions[label] = {
                "commit": commit, "parents": parents, "inputs": inputs, "outputs": outputs
            }

    return {"approved_base_commit": approved, "revisions": revisions}


if __name__ == "__main__":
    sys.stdout.buffer.write((json.dumps(compare(), indent=2) + "\n").encode("utf-8"))
