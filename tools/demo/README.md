# Guide videos

`record.mjs` records the short videos shown on the landing page ("How it works") and in the app
(**Help & guides** and the first-visit welcome tour). Each one is a scripted walk through the real
app on a 390×844 phone screen, with title cards and captions explaining when, why and how.

The guide text (titles, when, why and steps) lives in `frontend/src/lib/guides.ts`. Keep it in
step with the scenarios in `record.mjs`.

## Re-recording

Use a throwaway server with an empty data folder and no cloud keys, so nothing touches real data:

```bash
cd tools/demo && npm install && npx playwright install chromium ffmpeg
```

```bash
FERLANCE_EXPORT_BUCKET= AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= FERLANCE_DATA_DIR=$(mktemp -d) .venv/bin/uvicorn backend.main:app --port 8782
```

```bash
python tools/verify/seed.py http://localhost:8782
```

```bash
node tools/demo/record.mjs http://localhost:8782 frontend/public/assets/demo
```

Set `ONLY=credit,stock` to record only some scenarios. The output is `<slug>.webm` (VP9, about 1 MB)
and a `<slug>.jpg` poster for each scenario. Frames come from Chrome's screencast and are encoded
with Playwright's bundled ffmpeg, so no system ffmpeg is needed.
