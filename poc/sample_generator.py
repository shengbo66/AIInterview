"""Generate good/medium/poor synthetic interview samples using Claude + Polly."""
import argparse
import subprocess
import json
from pathlib import Path
import boto3
from config import REGION, POLLY_VOICE_ZH, POLLY_VOICE_EN, POLLY_ENGINE, PRICING
from claude_client import invoke_text
from shared.eval_core.prompt_template import sample_generation_prompt


QUESTIONS = {
    "en": "Tell me about a time you had to resolve a conflict with a teammate.",
    "zh": "请讲一次你和同事之间发生冲突并解决的经历。",
}


def generate_script(quality: str, language: str, question: str) -> tuple[str, float]:
    """Claude generates candidate answer text. Returns (text, cost_usd)."""
    prompt = sample_generation_prompt(quality, language, question)
    text, meta = invoke_text(prompt)
    return text, meta["cost_usd"]


def synthesize_audio(text: str, language: str, out_mp3: Path) -> float:
    """Polly synthesize -> MP3. Returns cost_usd."""
    polly = boto3.client("polly", region_name=REGION)
    voice = POLLY_VOICE_ZH if language == "zh" else POLLY_VOICE_EN
    resp = polly.synthesize_speech(
        Text=text, OutputFormat="mp3", VoiceId=voice, Engine=POLLY_ENGINE,
        LanguageCode="cmn-CN" if language == "zh" else "en-US",
    )
    out_mp3.write_bytes(resp["AudioStream"].read())
    cost = len(text) / 1_000_000 * PRICING["polly_neural_per_1m_char"]
    return cost


def convert_to_wav(in_mp3: Path, out_wav: Path) -> None:
    """Use ffmpeg to convert MP3 to 16 kHz mono WAV (Transcribe friendly)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(in_mp3), "-ar", "16000", "-ac", "1", str(out_wav)],
        check=True, capture_output=True,
    )


def generate_sample_set(language: str, out_dir: Path) -> dict:
    """Generate good/medium/poor sample set. Returns manifest dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    question = QUESTIONS[language]
    manifest = {"language": language, "question": question, "samples": {}, "total_cost_usd": 0.0}

    for quality in ["good", "medium", "poor"]:
        print(f"  → Generating [{quality}] script via Claude...")
        script, script_cost = generate_script(quality, language, question)
        mp3_path = out_dir / f"sample-{quality}-{language}.mp3"
        wav_path = out_dir / f"sample-{quality}-{language}.wav"
        script_path = out_dir / f"sample-{quality}-{language}.txt"

        script_path.write_text(script, encoding="utf-8")
        print(f"  → Synthesizing audio via Polly ({len(script)} chars)...")
        polly_cost = synthesize_audio(script, language, mp3_path)
        print(f"  → Converting to WAV 16kHz mono...")
        convert_to_wav(mp3_path, wav_path)

        total = script_cost + polly_cost
        manifest["samples"][quality] = {
            "script": script, "mp3": str(mp3_path), "wav": str(wav_path),
            "txt": str(script_path), "cost_usd": round(total, 4),
        }
        manifest["total_cost_usd"] += total
        print(f"  ✓ [{quality}] done, cost=${total:.4f}")

    manifest["total_cost_usd"] = round(manifest["total_cost_usd"], 4)
    (out_dir / f"manifest-{language}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--language", choices=["en", "zh"], default="en")
    p.add_argument("--out", type=Path, default=Path("samples"))
    args = p.parse_args()

    print(f"Generating {args.language} samples → {args.out}/")
    m = generate_sample_set(args.language, args.out)
    print(f"\n✅ Done. Total cost: ${m['total_cost_usd']:.4f}")
    print(f"Manifest: {args.out}/manifest-{args.language}.json")


if __name__ == "__main__":
    main()
