"""CLI: evaluate a single Q&A audio file. Outputs JSON report."""
import argparse
import json
from pathlib import Path
from evaluator import evaluate_one


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True, type=Path)
    p.add_argument("--question", required=True)
    p.add_argument("--company", default="Generic Tech Company")
    p.add_argument("--role", default="Software Engineer")
    p.add_argument("--language", choices=["en", "zh"], default="en")
    p.add_argument("--style-tags", nargs="*", default=None)
    p.add_argument("--out", type=Path, default=None, help="Output JSON path (default: results/<audio_stem>.json)")
    args = p.parse_args()

    print(f"🎤 Evaluating: {args.audio}")
    print(f"   Question: {args.question}")
    print(f"   Company: {args.company} / Role: {args.role} / Lang: {args.language}")

    result = evaluate_one(
        audio_path=str(args.audio),
        question=args.question,
        company=args.company,
        role=args.role,
        language=args.language,
        style_tags=args.style_tags,
    )

    out_path = args.out or Path("results") / f"{args.audio.stem}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    ev = result["evaluation"]
    print(f"\n✅ Done in {result['elapsed_sec']}s, cost=${result['cost_usd']:.4f}")
    print(f"   Content: {ev['content_score']}  Expression: {ev['expression_score']}  Voice: {ev['voice_score']}")
    print(f"   Overall: {ev['overall_score']} → {ev['overall_result']}")
    print(f"📁 Report: {out_path}")


if __name__ == "__main__":
    main()
