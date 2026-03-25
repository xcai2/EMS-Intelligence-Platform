# Sharing the Pre-Built ChromaDB (No Re-Embedding)

If someone has already run the embedding pipeline and built `chromadb_store/`, teammates **do not need to re-run** the long embedding process. They can use the same ChromaDB folder.

## Why no re-embedding?

- **Document embeddings** are stored inside `chromadb_store/`. That folder contains all vectors, document text, and metadata.
- At runtime the backend only uses the embedding model to convert **the user's query** into a vector, then runs similarity search in ChromaDB. It does not re-embed the documents.

So: share the folder → teammates put it in the project root → they run the app. No `build_chromadb.py` or `reindex_benchmark.py` needed.

## How to share

1. **`chromadb_store/` is in `.gitignore`**  
   It will not be pushed to Git. Share it by:
   - Zipping the folder and sending via Slack/Drive/WeChat, or
   - Uploading to shared storage and having teammates download it.

2. **Where to put it**  
   Teammates should place the unzipped `chromadb_store` folder at the **project root** (same level as `backend/`, `frontend/`, `scripts/`):

   ```
   Flex-Practicum-Project-2026/
   ├── chromadb_store/    ← put the shared folder here
   ├── backend/
   ├── frontend/
   ├── scripts/
   └── ...
   ```

3. **First run on a new machine**  
   The first time the backend starts, it will download the **embedding model** (e.g. `all-mpnet-base-v2`) once for encoding queries. This is a one-time download (a few hundred MB), not a re-embedding of all documents.

## Checklist for teammates

- [ ] Get the `chromadb_store` folder from the person who ran embedding (zip/cloud).
- [ ] Put `chromadb_store` at project root (see structure above).
- [ ] Copy `backend/.env.example` to `backend/.env` and set `OPENAI_API_KEY`.
- [ ] Install backend deps: `pip install -r backend/requirements.txt`.
- [ ] Start backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8001` (or from `backend/` with `python -m uvicorn main:app ...`).
- [ ] No need to run `scripts/build_chromadb.py` or `scripts/reindex_benchmark.py`.

## If they add new documents later

If the team adds new PDFs/HTMLs and wants them searchable, then someone needs to run the embedding pipeline again (e.g. `build_chromadb.py` or company-specific reindex scripts). After that, they can re-share the updated `chromadb_store` so others still don’t have to re-embed from scratch.
