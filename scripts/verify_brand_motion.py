#!/usr/bin/env python3
"""Compare native cosmetic motion against the canonical JavaScript fixtures."""
import argparse
import json
import math
from pathlib import Path
import re


def verify(expected, actual):
    def compare(want, got, location):
        if isinstance(want, dict):
            for key, value in want.items():
                if key in ("name", "d"):
                    continue
                assert key in got, location + "." + key
                compare(value, got[key], location + "." + key)
            if "d" in want:
                numbers = list(map(float, re.findall(r"-?\d+(?:\.\d+)?", want["d"])))
                compare([numbers[i:i+2] for i in range(0, len(numbers), 2)], got["detailed"], location + ".detailed")
        elif isinstance(want, list):
            assert len(want) == len(got), location
            for i, (a, b) in enumerate(zip(want, got)):
                compare(a, b, location + "[" + str(i) + "]")
        elif isinstance(want, (float, int)):
            assert isinstance(got, (float, int)) and math.isclose(want, got, rel_tol=1e-12, abs_tol=1e-8), (location, want, got)
        else:
            assert want == got, (location, want, got)
    compare(expected["samples"], actual, "motion")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actual", type=Path)
    args = parser.parse_args()
    expected = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/brand-motion.json").read_text())
    verify(expected, json.loads(args.actual.read_text(encoding="utf-8-sig")))
    print(json.dumps({"brand": "1.3.0", "seeds": 4, "scenes_per_seed": 10, "native_parity": True}))
