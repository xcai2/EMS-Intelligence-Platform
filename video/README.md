# EMS Intelligence Platform — Automated Video Production

Fully automated pipeline: AI voiceover → auto-subtitles → Playwright screen recording → FFmpeg assembly.

## Prerequisites

| Tool | Status | Install |
|------|--------|---------|
| Node.js ≥ 18 | ✅ | — |
| Python ≥ 3.10 | ✅ | — |
| ffmpeg | ✅ | `brew install ffmpeg` |
| elevenlabs (Python) | ❌ | `pip install elevenlabs` |
| openai (Python) | ✅ | — |
| playwright (Node) | ❌ | see below |

## Setup (one-time)

```bash
# 1. Install Python dependencies
pip install elevenlabs openai

# 2. Install Playwright + Chromium
cd video/
npm install
npx playwright install chromium
```

## Running the pipeline

### Step 1 — Start the dev servers

Open two terminal tabs:

```bash
# Tab 1: Frontend
cd frontend && npm run dev

# Tab 2: Backend
cd backend && uvicorn main:app --host 0.0.0.0 --port 8001
```

Wait until both are running and the browser opens at http://localhost:3000 with data loaded.

### Step 2 — Set API keys

```bash
export ELEVENLABS_API_KEY=your_elevenlabs_key_here
export OPENAI_API_KEY=your_openai_key_here
```

### Step 3 — Generate voiceover + subtitles

```bash
cd video/
python generate_voice.py
```

Outputs: `output/voiceover.mp3` and `output/subtitles.srt`

### Step 4 — Record the screen

```bash
node record_demo.js
```

A Chromium window opens and navigates automatically for ~3 minutes.
Output: `output/screen_recording.webm`

### Step 5 — Assemble final video

```bash
bash assemble.sh
```

Output: `output/final_output.mp4`

---

## Output files

```
video/
├── transcript.txt              spoken text (edit to customize)
├── record_demo.js              Playwright automation script
├── generate_voice.py           ElevenLabs TTS + Whisper subtitles
├── assemble.sh                 FFmpeg merge + subtitle burn
├── package.json
└── output/
    ├── voiceover.mp3           AI voiceover
    ├── subtitles.srt           auto-generated subtitles
    ├── screen_recording.webm   raw Playwright recording
    ├── screen_recording.mp4    converted mp4
    ├── merged.mp4              video + audio merged
    └── final_output.mp4        ← final deliverable
```

## Customization

- **Transcript**: edit `transcript.txt` — re-run `generate_voice.py` (delete `output/voiceover.mp3` first to force regeneration)
- **Timing**: adjust `sleep()` values in `record_demo.js` to sync with your voiceover pace
- **Voice**: change `VOICE_ID` in `generate_voice.py` — alternatives: Rachel (`21m00Tcm4TlvDq8ikWAM`), Brian (`nPczCjzI2devNBz1zQrb`)
- **Subtitles style**: edit the `STYLE` variable in `assemble.sh`

## Cost

| Service | Cost |
|---------|------|
| ElevenLabs (George voice, ~430 words) | ~$0.50 with Creator plan / free tier may hit limit |
| OpenAI Whisper API (~3 min audio) | ~$0.02 |
| Playwright + ffmpeg | free |
