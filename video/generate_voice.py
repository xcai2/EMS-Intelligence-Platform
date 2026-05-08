"""
EMS Intelligence Platform — Voice + Subtitle Generator

Steps:
  1. export ELEVENLABS_API_KEY=your_key
  2. export OPENAI_API_KEY=your_key
  3. python generate_voice.py

Outputs:
  output/voiceover.mp3   — AI voiceover (ElevenLabs George)
  output/subtitles.srt   — auto-generated subtitles (Whisper)
"""

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

TRANSCRIPT_PATH = SCRIPT_DIR / "transcript.txt"
VOICEOVER_PATH  = OUTPUT_DIR / "voiceover.mp3"
SUBTITLES_PATH  = OUTPUT_DIR / "subtitles.srt"

VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # ElevenLabs: George (calm, professional)
ELEVEN_MODEL = "eleven_turbo_v2_5"


def check_env():
    missing = [k for k in ("ELEVENLABS_API_KEY", "OPENAI_API_KEY") if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Set them with:\n  export ELEVENLABS_API_KEY=...\n  export OPENAI_API_KEY=...")
        sys.exit(1)


def gen_voice():
    if VOICEOVER_PATH.exists():
        print(f"⏩ Skipping voice gen — {VOICEOVER_PATH} already exists")
        return

    print("🎙  Generating voiceover with ElevenLabs…")
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        print("ERROR: elevenlabs package not installed. Run: pip install elevenlabs")
        sys.exit(1)

    transcript = TRANSCRIPT_PATH.read_text(encoding="utf-8").strip()
    el = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

    audio = el.text_to_speech.convert(
        voice_id=VOICE_ID,
        text=transcript,
        model_id=ELEVEN_MODEL,
        voice_settings={
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.2,
            "use_speaker_boost": True,
        },
    )

    with open(VOICEOVER_PATH, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    print(f"✅ voiceover.mp3 ({VOICEOVER_PATH.stat().st_size // 1024} KB)")


def gen_subtitles():
    if SUBTITLES_PATH.exists():
        print(f"⏩ Skipping subtitles — {SUBTITLES_PATH} already exists")
        return

    print("📝 Generating subtitles with Whisper…")
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: openai package not installed. Run: pip install openai")
        sys.exit(1)

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with open(VOICEOVER_PATH, "rb") as f:
        srt = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="srt",
            language="en",
        )

    SUBTITLES_PATH.write_text(srt, encoding="utf-8")
    print(f"✅ subtitles.srt")


if __name__ == "__main__":
    check_env()
    gen_voice()
    gen_subtitles()
    print("\nDone! Next step: run record_demo.js, then assemble.sh")
