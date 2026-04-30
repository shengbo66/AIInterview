"""Logging config: duplicate stdout + write to /tmp/interviewer-backend.log

Import this module (or its `setup_logging` function) early during app
startup to enable. Designed for development / triage; not for prod.
"""
import logging
import logging.handlers
import sys
from pathlib import Path

LOG_FILE = Path("/tmp/interviewer-backend.log")
FMT = "%(asctime)s %(levelname)-5s %(name)-32s %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    # Idempotent: don't stack handlers on reload
    if any(getattr(h, "_interviewer_tag", False) for h in root.handlers):
        return

    root.setLevel(level)
    fmt = logging.Formatter(FMT, datefmt="%H:%M:%S")

    # File — rotates at 10 MB to stay manageable
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(level)
    fh._interviewer_tag = True  # type: ignore[attr-defined]
    root.addHandler(fh)

    # Console — so uvicorn --reload still shows progress
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(level)
    sh._interviewer_tag = True  # type: ignore[attr-defined]
    root.addHandler(sh)

    # Our modules
    for name in (
        "interviewer.demo_bidi",
        "interviewer.bidi_session",
        "strands",
        "uvicorn.error",
    ):
        logging.getLogger(name).setLevel(level)

    root.info("logging initialized -> %s", LOG_FILE)
