# Flex Competitive Intelligence Platform - Complete Setup Guide

> **Last updated:** April 20, 2026
>
> Follow every step below in order. If you get stuck, check the [Troubleshooting](#troubleshooting) section at the bottom before asking for help.

---

## Table of Contents

1. [Prerequisites (Install These First)](#1-prerequisites-install-these-first)
2. [Clone the Repository](#2-clone-the-repository)
3. [Set Up API Keys](#3-set-up-api-keys)
4. [Backend Setup (Python)](#4-backend-setup-python)
5. [Frontend Setup (Node.js)](#5-frontend-setup-nodejs)
6. [Build the ChromaDB Vector Database](#6-build-the-chromadb-vector-database)
7. [Running the Application](#7-running-the-application)
8. [Verify Everything Works](#8-verify-everything-works)
9. [Available Pages](#9-available-pages)
10. [Stopping the Servers](#10-stopping-the-servers)
11. [Daily Workflow (After Initial Setup)](#11-daily-workflow-after-initial-setup)
12. [Pulling Latest Changes](#12-pulling-latest-changes)
13. [Project Structure Overview](#13-project-structure-overview)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites (Install These First)

You need **three things** installed on your computer before anything else.

### A. Python 3.10 or higher

**Check if you already have it:**

```bash
python3 --version
```

You should see `Python 3.10.x` or higher. If not, install it:

- **Mac:** Open Terminal and run:
  ```bash
  brew install python
  ```
  Don't have Homebrew? Install it first: https://brew.sh (paste the command from that page into Terminal)
- **Windows:** Download from [https://www.python.org/downloads/](https://www.python.org/downloads/) — **IMPORTANT:** Check the box that says **"Add Python to PATH"** during installation.

### B. Node.js 18 or higher

**Check if you already have it:**

```bash
node --version
```

You should see `v18.x.x` or higher. If not:

- **Mac:**
  ```bash
  brew install node
  ```
- **Windows:** Download from [https://nodejs.org/](https://nodejs.org/) (choose the LTS version)

### C. Git

**Check if you already have it:**

```bash
git --version
```

If not installed:

- **Mac:** It will prompt you to install Xcode Command Line Tools. Click "Install".
- **Windows:** Download from [https://git-scm.com/downloads](https://git-scm.com/downloads)

---

## 2. Clone the Repository

Open your Terminal (Mac) or Command Prompt/PowerShell (Windows) and run:

```bash
git clone https://github.com/xcai2/Flex-Practicum-Project-2026.git
```

Then navigate into the project folder:

```bash
cd Flex-Practicum-Project-2026
```

> **Where does this go?** It creates a folder called `Flex-Practicum-Project-2026` in whatever directory you ran the command from. If you want it on your Desktop, first run `cd ~/Desktop` (Mac) or `cd %USERPROFILE%\Desktop` (Windows) before cloning.

---

## 3. Set Up API Keys

The app needs API keys to work. You need to create **two** environment files.

### A. Backend API Keys (Required)

Create a file called `.env` inside the `backend/` folder:

**Mac/Linux:**

```bash
cp backend/.env.example backend/.env
```

**Windows (PowerShell):**

```powershell
Copy-Item backend\.env.example backend\.env
```

Now open `backend/.env` in any text editor (VS Code, Notepad, TextEdit) and replace the placeholder values:

```
# LLM Provider: "openai" (default) | "anthropic" | "gemini"
LLM_PROVIDER=openai

# REQUIRED (default LLM) - Get from https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-your-openai-key-here

# OPTIONAL - only needed if switching LLM_PROVIDER to "anthropic"
# Get from https://console.anthropic.com/
ANTHROPIC_API_KEY=

# OPTIONAL - only needed if switching LLM_PROVIDER to "gemini"
# Get from https://aistudio.google.com/
GOOGLE_API_KEY=

# OPTIONAL but recommended - web search (FREE: 2,000 queries/month)
# Get from https://brave.com/search/api/
BRAVE_API_KEY=BSA-YOUR-ACTUAL-KEY-HERE

# Leave this as-is
SEC_USER_AGENT=CapExIntel/1.0 (your-email@example.com)
```

#### How to get the API keys:


| Key                 | Where to get it                                                                                                    | Cost                          | Required?              |
| ------------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------- | ---------------------- |
| **OPENAI_API_KEY**  | [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys) → Sign up → Create key              | ~$20-50/month usage           | **Yes** (default LLM)  |
| **ANTHROPIC_API_KEY** | [https://console.anthropic.com/](https://console.anthropic.com/) → Sign up → API Keys → Create Key             | ~$20-50/month usage           | Optional (alt LLM)     |
| **GOOGLE_API_KEY**  | [https://aistudio.google.com/](https://aistudio.google.com/) → Get API Key                                        | Free tier available           | Optional (alt LLM)     |
| **BRAVE_API_KEY**   | [https://brave.com/search/api/](https://brave.com/search/api/) → Sign up → Get free API key                       | FREE (2,000 queries/month)    | Optional (web search)  |


> **Ask the team lead** if you don't want to create your own keys — they can share the existing ones.

### B. Frontend Environment (Required)

Create a file called `.env.local` inside the `frontend/` folder:

**Mac/Linux:**

```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8001" > frontend/.env.local
```

**Windows (PowerShell):**

```powershell
"NEXT_PUBLIC_API_URL=http://localhost:8001" | Out-File -Encoding utf8 frontend\.env.local
```

That's it for frontend — it just needs to know where the backend is running.

---

## 4. Backend Setup (Python)

From the project root folder (`Flex-Practicum-Project-2026/`), run:

```bash
pip install -r backend/requirements.txt
```

> **This will take 3-5 minutes** the first time because it downloads AI models and dependencies (~1 GB).

**If `pip` doesn't work**, try:

```bash
pip3 install -r backend/requirements.txt
```

**If you see permission errors**, try:

```bash
pip install --user -r backend/requirements.txt
```

### Optional: Use a Virtual Environment (Recommended)

A virtual environment keeps project dependencies isolated. This is recommended but not strictly required.

**Mac/Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

**Windows:**

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
```

> **Remember:** If you use a virtual environment, you need to activate it every time you open a new terminal to work on the project:
>
> - Mac/Linux: `source venv/bin/activate`
> - Windows: `venv\Scripts\activate`
>
> You'll know it's active when you see `(venv)` at the start of your terminal prompt.

---

## 5. Frontend Setup (Node.js)

From the project root folder, run:

```bash
cd frontend
npm install
cd ..
```

> **This will take 1-2 minutes** the first time. You'll see lots of output — that's normal. As long as it doesn't end with `ERR!`, you're fine.

---

## 6. Build the ChromaDB Vector Database

The app uses a vector database (ChromaDB) to search through SEC filings. This database is NOT included in the repo (it's ~570 MB), so you need to build it locally.

> **Note:** This step only needs to be done **once**. It takes about 15-30 minutes depending on your computer. You can skip it initially if you just want to explore the UI — the app will work but queries won't return document results.

**Before running this**, make sure the company data folders are present in `data/raw/` (`Flex/`, `Jabil/`, `Celestica/`, `Benchmark/`, `Sanmina/`, `Plexus/`). They should already be there from cloning.

From the project root folder:

```bash
python3 scripts/build_chromadb.py
```

You'll see output like:

```
======================================================================
  MULTI-COMPANY CAPEX — CHROMADB EMBEDDING PIPELINE
======================================================================
  Loading embedding model (all-mpnet-base-v2)...
  ✓ Model loaded (768-dim vectors)

  Scanning company folders...
  📂 Flex         → 27 files
  📂 Jabil        → 84 files
  📂 Celestica    → 77 files
  📂 Benchmark    → 111 files
  📂 Sanmina      → 106 files
  ...
```

Wait until you see `✅ ChromaDB ready for all companies`.

> The script automatically finds the company data folders relative to the project root. No path configuration needed.

---

## 7. Running the Application

You need **two terminal windows** running at the same time — one for the backend, one for the frontend.

### Terminal 1: Start the Backend

Open a terminal, navigate to the project root, and run:

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

**Wait until you see output like this:**

```
✓ Embedding model pre-loaded
✓ ChromaDB connected: 19050 documents
✓ Scheduler started for automated SEC filing checks
INFO:     Uvicorn running on http://0.0.0.0:8001
```

> **Leave this terminal running.** Don't close it.

### Terminal 2: Start the Fvrontend

Open a **second** terminal window, navigate to the project, and run:

```bash
cd Flex-Practicum-Project-2026/frontend
npm run dev
```

**Wait until you see:**

```
  ▲ Next.js 16.x.x
  - Local: http://localhost:3000

  ✓ Ready in Xms
```

> **Leave this terminal running too.** Don't close it.

---

## 8. Verify Everything Works

### Step 1: Open the App

Open your browser and go to: **[http://localhost:3000](http://localhost:3000)**

You should see the app's main page.

### Step 2: Check the Backend Health

Open a **third** terminal (or a new browser tab) and go to:

**[http://localhost:8001/api/health](http://localhost:8001/api/health)**

You should see something like:

```json
{
  "status": "healthy",
  "chromadb": {
    "connected": true,
    "documents": 19050,
    "companies": {
      "Flex": 3200,
      "Jabil": 5100,
      ...
    }
  }
}
```

If `"connected": true` and documents > 0, everything is working.

### Step 3: Test the Dashboard

Go to: **[http://localhost:3000/dashboard](http://localhost:3000/dashboard)**

You should see analytics charts and company data.

### Step 4: Test the Chat

Go to: **[http://localhost:3000/chat](http://localhost:3000/chat)**

Try asking: *"What is Flex's capital expenditure for 2024?"*

You should get an AI-generated response with data from SEC filings.

---

## 9. Available Pages


| Page                        | URL                                                                                            | What It Does                                                   |
| --------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **Dashboard**               | [http://localhost:3000/dashboard](http://localhost:3000/dashboard)                             | Overview with charts, metrics, and company summaries           |
| **AI Chat**                 | [http://localhost:3000/chat](http://localhost:3000/chat)                                       | Ask questions about companies — AI answers using SEC filings   |
| **Companies**               | [http://localhost:3000/companies](http://localhost:3000/companies)                             | Browse all 6 tracked EMS companies                             |
| **Analysis**                | [http://localhost:3000/analysis](http://localhost:3000/analysis)                               | Detailed CapEx analysis and comparisons                        |
| **Analyst View**            | [http://localhost:3000/analyst-view](http://localhost:3000/analyst-view)                       | Analyst intelligence: consensus, price targets, ratings feed   |
| **Facility Map**            | [http://localhost:3000/map](http://localhost:3000/map)                                         | Interactive map of EMS facilities across 6 companies           |
| **AI Investments**          | [http://localhost:3000/ai-investments](http://localhost:3000/ai-investments)                   | AI-related investment trends across EMS peers                  |
| **Competitor Investments**  | [http://localhost:3000/competitor-investments](http://localhost:3000/competitor-investments)   | Competitor capex and investment comparison                     |
| **News Feed**               | [http://localhost:3000/news](http://localhost:3000/news)                                       | Latest news about tracked companies                            |
| **Reports**                 | [http://localhost:3000/reports](http://localhost:3000/reports)                                 | Generate PDF/Excel/PowerPoint reports                          |
| **Alerts**                  | [http://localhost:3000/alerts](http://localhost:3000/alerts)                                   | Manage notifications for SEC filings and anomalies             |
| **Calendar**                | [http://localhost:3000/calendar](http://localhost:3000/calendar)                               | Earnings calendar                                              |
| **Settings**                | [http://localhost:3000/settings](http://localhost:3000/settings)                               | Ingestion and configuration settings                           |
| **Compare**                 | [http://localhost:3000/compare](http://localhost:3000/compare)                                 | Side-by-side company comparison                                |


### Backend API Docs (for developers)

The backend has auto-generated API docs at: **[http://localhost:8001/docs](http://localhost:8001/docs)**

This is a Swagger UI where you can test every API endpoint directly.

---

## 10. Stopping the Servers

Press `Ctrl + C` in each terminal window to stop the servers.

---

## 11. Daily Workflow (After Initial Setup)

After the first-time setup, here's all you need to do each time you work on the project:

```bash
# 1. Open Terminal, navigate to the project
cd Flex-Practicum-Project-2026

# 2. (If using virtual env) Activate it
source venv/bin/activate       # Mac/Linux
# venv\Scripts\activate        # Windows

# 3. Start backend (Terminal 1)
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001

# 4. Start frontend (Terminal 2)
cd frontend && npm run dev
```

Then open **[http://localhost:3000](http://localhost:3000)** in your browser.

---

## 12. Pulling Latest Changes

When someone on the team pushes updates, pull them:

```bash
cd Flex-Practicum-Project-2026
git pull origin main
```

Then reinstall dependencies in case they changed:

```bash
# Backend
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

Restart both servers after pulling.

---

## 13. Project Structure Overview

```
Flex-Practicum-Project-2026/
│
├── backend/                    ← Python FastAPI backend
│   ├── main.py                 ← App entry point
│   ├── requirements.txt        ← Python dependencies
│   ├── .env                    ← YOUR API keys (not in git)
│   ├── .env.example            ← Template for .env
│   ├── core/                   ← Config, database, caching
│   ├── rag/                    ← AI chat: retriever, generator, web search
│   ├── analytics/              ← Sentiment, anomaly detection, trends
│   ├── ingestion/              ← SEC scraper, news, patents, jobs
│   ├── api/routes/             ← API endpoint definitions
│   ├── alerts/                 ← Email and Slack notifications
│   ├── exports/                ← PDF, Excel, PowerPoint generation
│   └── reports/                ← Auto-summarizer, calendar
│
├── frontend/                   ← Next.js React frontend
│   ├── src/app/                ← Page routes (dashboard, chat, etc.)
│   ├── src/components/         ← Reusable UI components
│   ├── src/lib/                ← API client, types, utilities
│   ├── package.json            ← Node.js dependencies
│   └── .env.local              ← Frontend config (not in git)
│
├── chromadb_store/             ← Vector database (built locally, not in git)
│
├── data/
│   ├── raw/                   ← Company SEC filings & documents
│   │   ├── Flex/              ← Flex filings (HTML)
│   │   ├── Jabil/             ← Jabil filings (PDF)
│   │   ├── Celestica/         ← Celestica filings (PDF)
│   │   ├── Benchmark/         ← Benchmark filings (HTM)
│   │   └── Sanmina/           ← Sanmina filings (PDF)
│   └── sec_filings/           ← Auto-downloaded SEC filings
│
├── scripts/                    ← CLI tools and build scripts
│   └── build_chromadb.py      ← Script to build ChromaDB from company docs
│
├── tools/                      ← Standalone utilities
│   ├── analysis_tool/         ← Streamlit analysis prototype
│   └── verify/                ← RAG evaluation tools
│
├── SETUP.md                    ← THIS FILE
└── README.md                   ← Project overview and architecture
```

---

## 14. Troubleshooting

### Installation Issues


| Problem                      | Solution                                                                                                            |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `python3: command not found` | Install Python. On Windows, try `python` instead of `python3`.                                                      |
| `pip: command not found`     | Try `pip3` instead of `pip`. Or use `python3 -m pip install ...`                                                    |
| `node: command not found`    | Install Node.js from [https://nodejs.org/](https://nodejs.org/)                                                     |
| `git: command not found`     | On Mac, accept the Xcode prompt. On Windows, install from [https://git-scm.com/](https://git-scm.com/)              |
| `brew: command not found`    | Install Homebrew: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| Permission denied errors     | Add `--user` flag: `pip install --user -r backend/requirements.txt`                                                 |
| `npm ERR! code ERESOLVE`     | Try: `cd frontend && rm -rf node_modules package-lock.json && npm install`                                          |


### Backend Issues


| Problem                                      | Solution                                                                                                               |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'xxx'` | Run `pip install -r backend/requirements.txt` again                                                                    |
| `No module named 'backend'`                  | Make sure you're running the command from the **project root** folder, not from inside `backend/`                      |
| `Address already in use (port 8001)`         | Another process is using that port. Kill it: `lsof -i :8001` then `kill <PID>`. Or use a different port: `--port 8002` |
| `ChromaDB connection failed`                 | You haven't built the database yet. See [Step 6](#6-build-the-chromadb-vector-database)                                |
| `ANTHROPIC_API_KEY not set`                  | Check that `backend/.env` exists and has your key. Make sure there are no spaces around the `=` sign                   |
| Backend starts but chat doesn't work         | Check that `ANTHROPIC_API_KEY` in `backend/.env` is valid and has credits                                              |
| `Embedding model failed to load`             | First run takes a few minutes to download the model (~400 MB). Make sure you have internet.                            |


### Frontend Issues


| Problem                                   | Solution                                                                                       |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `npm install` fails                       | Delete `frontend/node_modules/` and `frontend/package-lock.json`, then run `npm install` again |
| Page shows "Failed to connect to backend" | Make sure the backend is running on port 8001 in a separate terminal                           |
| Blank page / nothing loads                | Check browser console (F12 → Console tab) for errors. Usually means backend isn't running      |
| Port 3000 already in use                  | The frontend will automatically try port 3001. Check the terminal output for the actual URL    |
| CSS looks broken                          | Run `cd frontend && npm install && npm run dev`                                                |


### ChromaDB Build Issues


| Problem                          | Solution                                                                                   |
| -------------------------------- | ------------------------------------------------------------------------------------------ |
| `No files found`                 | Make sure you're running the script from the project root (`Flex-Practicum-Project-2026/`) |
| `Skipping [company] — not found` | Some companies might not have all subfolders. This is OK — it processes what it finds      |
| Script is very slow              | Normal — it's embedding ~400 documents. Takes 15-30 minutes on most machines               |
| `OutOfMemoryError`               | Close other applications. The embedding model needs ~2 GB RAM                              |


### General Tips

- **Always run commands from the project root** (`Flex-Practicum-Project-2026/`), not from subfolders
- **Backend must start before frontend** — the frontend needs the backend API to be available
- **Restart both servers** after pulling new changes from git
- **Check the API docs** at [http://localhost:8001/docs](http://localhost:8001/docs) for testing endpoints
- **Browser cache** can cause issues — try hard refresh (`Cmd+Shift+R` on Mac, `Ctrl+Shift+R` on Windows)

---

## Quick Reference Card

```
┌──────────────────────────────────────────────────┐
│               QUICK START                        │
│                                                  │
│  Terminal 1 (Backend):                           │
│  $ cd Flex-Practicum-Project-2026                │
│  $ python3 -m uvicorn backend.main:app \         │
│      --host 0.0.0.0 --port 8001                  │
│                                                  │
│  Terminal 2 (Frontend):                          │
│  $ cd frontend                                   │
│  $ npm run dev                                   │
│                                                  │
│  Browser: http://localhost:3000                  │
│  API Docs: http://localhost:8001/docs            │
│  Health: http://localhost:8001/api/health        │
└──────────────────────────────────────────────────┘


python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
```






