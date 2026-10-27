"""Application version shared by source builds and packaged runtimes."""
from pathlib import Path
import re

VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", VERSION):
    raise RuntimeError("Invalid application VERSION")
