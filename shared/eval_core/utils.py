"""Pure-Python utilities (no AWS deps) — kept testable in isolation."""
import json


def parse_json_strict(text: str) -> dict:
    """Parse JSON, handling accidental markdown code fences like ```json ... ```."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        t = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    return json.loads(t)
