"""Fresh process preserves the accepted SDK and blocks network during inference."""
import json
from pathlib import Path
import sys

from .contracts import WorkflowError, write_json
from .pipeline import Config, synthesize


def main():
    out = Path(sys.argv[1]).resolve()
    try:
        config = Config.load(out / "runtime-config.json")
        snapshot = json.loads((out / "input.json").read_bytes())
        synthesize(config, snapshot, out)
        write_json(out / "tts-status.json", {"status": "pass"})
        return 0
    except Exception as error:
        # No traceback, input text or provider credential in stdout/stderr.
        code = error.code if isinstance(error, WorkflowError) else type(error).__name__
        write_json(out / "tts-status.json", {"status": "failed", "code": code})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
