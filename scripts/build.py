"""Build the static site with a JSON-only health response from the archive index."""

import json
import shutil
from pathlib import Path


def build_site(source: Path, output: Path) -> None:
    index = json.loads((source / "days" / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, list):
        raise ValueError("days/index.json must contain an array")
    payload = json.dumps({"days": len(index), "status": "ok"}, separators=(",", ":")) + "\n"

    # Keep build tools, hidden files, and private state out of the public artifact.
    shutil.copytree(
        source,
        output,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".*", "_*", "scripts", "README.md", "health"),
    )
    health_dir = output / "health"
    health_dir.mkdir(exist_ok=True)
    # A directory index keeps /health visitable without triggering a download.
    # The response body is JSON only, despite Pages' text/html MIME type here.
    (health_dir / "index.html").write_text(payload, encoding="utf-8")
    (output / "health.json").write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    source = Path(__file__).resolve().parents[1]
    build_site(source, source / "_site")
