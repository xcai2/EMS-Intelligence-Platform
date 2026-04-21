# Flex Competitive Intelligence Platform — Setup Guide

> **Last updated:** April 20, 2026
>
> Follow the steps below in order. Never done this before? That's fine — every command is written out for you.

---

## What You'll Need First

Before anything else, make sure these three tools are installed.

| Tool | Check if installed | Install if missing |
|------|-------------------|--------------------|
| **Python 3.10+** | `python3 --version` | Mac: `brew install python` · Windows: [python.org](https://www.python.org/downloads/) *(check "Add to PATH")* |
| **Node.js 18+** | `node --version` | Mac: `brew install node` · Windows: [nodejs.org](https://nodejs.org/) (LTS version) |
| **Git** | `git --version` | Mac: accept the Xcode prompt · Windows: [git-scm.com](https://git-scm.com/downloads) |

> **Mac only:** If `brew` isn't installed, run this first:
> ```bash
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/xcai2/Flex-Practicum-Project-2026.git
cd Flex-Practicum-Project-2026
```

---

## Step 2 — Set Up API Keys

### Backend keys

Copy the template file:

```bash
# Mac/Linux
cp backend/.env.example backend/.env

# Windows (PowerShell)
Copy-Item backend\.env.example backend\.env
```

Open `backend/.env` and fill in your keys:

```
LLM_PROVIDER=openai

OPENAI_API_KEY=sk-your-key-here        # REQUIRED — get from platform.openai.com/api-keys
BRAVE_API_KEY=BSA-your-key-here        # Optional — free web search, brave.com/search/api

# Only needed if switching LLM_PROVIDER to "anthropic" or "gemini":
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=

SEC_USER_AGENT=CapExIntel/1.0 (your-email@example.com)
```

> **Ask the team lead** if you don't have keys — they can share the existing ones.

### Frontend config

```bash
# Mac/Linux
echo "NEXT_PUBLIC_API_URL=http://localhost:8001" > frontend/.env.local

# Windows (PowerShell)
"NEXT_PUBLIC_API_URL=http://localhost:8001" | Out-File -Encoding utf8 frontend\.env.local
```

---

## Step 3 — Install Dependencies

**Backend (Python):**

```bash
python3 -m venv .venv

# Mac/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r backend/requirements.txt
```

> This downloads ~1 GB of packages and AI models. Takes 3–5 minutes. Normal.
>
> **Every time** you open a new terminal to work on the project, activate the venv first (`source .venv/bin/activate`). You'll see `(.venv)` in your prompt when it's active.

**Frontend (Node.js):**

```bash
cd frontend && npm install && cd ..
```

> Takes 1–2 minutes. Lots of output is normal — as long as it doesn't end with `ERR!` you're fine.

---

## Step 4 — Build the Vector Database (First Time Only)

The app searches through SEC filings using a vector database. You need to build it once locally (~15–30 min).

```bash
python3 scripts/build_chromadb.py
```

Wait until you see `✅ ChromaDB ready for all companies`.

> You can skip this step to explore the UI first — everything works except document search in the Chat page.

---

## Step 5 — Run the App

You need **two terminal windows open at the same time**.

**Terminal 1 — Backend:**

```bash
source .venv/bin/activate    # (Windows: .venv\Scripts\activate)
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

Wait for: `INFO: Uvicorn running on http://0.0.0.0:8001`

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

Wait for: `✓ Ready — Local: http://localhost:3000`

**Then open your browser:** [http://localhost:3000](http://localhost:3000)

---

## Available Pages

| Page | URL | What it does |
|------|-----|--------------|
| Dashboard | [/dashboard](http://localhost:3000/dashboard) | Charts, metrics, company summaries |
| AI Chat | [/chat](http://localhost:3000/chat) | Ask questions — AI answers from SEC filings |
| Companies | [/companies](http://localhost:3000/companies) | Browse all 6 EMS companies |
| Analyst View | [/analyst-view](http://localhost:3000/analyst-view) | Analyst consensus, price targets, ratings feed |
| Facility Map | [/map](http://localhost:3000/map) | Interactive map of EMS facilities worldwide |
| AI Investments | [/ai-investments](http://localhost:3000/ai-investments) | AI-related investment trends across peers |
| Competitor Investments | [/competitor-investments](http://localhost:3000/competitor-investments) | CapEx and investment comparison |
| News Feed | [/news](http://localhost:3000/news) | Latest news for tracked companies |
| Calendar | [/calendar](http://localhost:3000/calendar) | Earnings calendar |
| Reports | [/reports](http://localhost:3000/reports) | Generate PDF/Excel/PowerPoint reports |
| Compare | [/compare](http://localhost:3000/compare) | Side-by-side company comparison |
| Alerts | [/alerts](http://localhost:3000/alerts) | Notifications for SEC filings and anomalies |
| Settings | [/settings](http://localhost:3000/settings) | Ingestion and configuration |

**Backend API docs (for developers):** [http://localhost:8001/docs](http://localhost:8001/docs)

---

## Daily Workflow

After initial setup, this is all you need each session:

```bash
# Terminal 1 — Backend
cd Flex-Practicum-Project-2026
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001

# Terminal 2 — Frontend
cd Flex-Practicum-Project-2026/frontend
npm run dev
```

---

## Pulling Updates from the Team

```bash
git pull origin main
pip install -r backend/requirements.txt   # picks up any new packages
cd frontend && npm install && cd ..       # picks up any new packages
```

Then restart both servers.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python3: command not found` | Install Python. On Windows try `python` instead of `python3` |
| `pip: command not found` | Try `pip3`, or `python3 -m pip install ...` |
| `No module named 'backend'` | Run uvicorn from the **project root**, not inside `backend/` |
| `Address already in use (port 8001)` | Run `lsof -i :8001` then `kill <PID>`, or use `--port 8002` |
| `npm ERR! code ERESOLVE` | `cd frontend && rm -rf node_modules package-lock.json && npm install` |
| Page shows "Failed to connect to backend" | Backend isn't running — start Terminal 1 first |
| Chat works but no document results | ChromaDB not built yet — run Step 4 |
| `OPENAI_API_KEY not set` | Check `backend/.env` exists and has your key (no spaces around `=`) |
| Embedding model slow to load | First run downloads ~400 MB — needs internet, takes a few minutes |
