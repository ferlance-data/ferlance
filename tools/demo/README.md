# Guide videos

`record.mjs` records the short videos shown on the landing page ("How it works") and in the app
(**Help & guides** and the first-visit welcome tour). Each one is a scripted walk through the real
app on a 390×844 phone screen, with title cards and captions explaining when, why and how.

The guide text (titles, when, why and steps) lives in `frontend/src/lib/guides.ts`. Keep it in
step with the scenarios in `record.mjs`.

## Re-recording

Use a throwaway server with an empty data folder and no cloud keys, so nothing touches real data:

```bash
cd tools/demo && npm install && npx playwright install chromium
```

The videos are H.264 MP4 so they play on every phone, iPhones included. Playwright's own ffmpeg
can't write H.264, so point `FFMPEG` at one that can. A system ffmpeg works, or the build that
ships with the `imageio-ffmpeg` Python package:

```bash
python3 -m venv /tmp/ff && /tmp/ff/bin/pip install imageio-ffmpeg
```

```bash
export FFMPEG=$(/tmp/ff/bin/python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
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

Set `ONLY=credit,stock` to record only some scenarios. The output is `<slug>.mp4` (H.264, about 250 KB)
and a `<slug>.jpg` poster for each scenario. Frames come from Chrome's screencast. The welcome
tour is skipped, and the AI explanation panel is hidden, because the recording server has no AI key.

## Narration (English, Twi, Ga, Ewe, Fante)

`voice.py` speaks the scripts in `frontend/src/lib/narration.json` and lays them over each silent
video. The output is `<slug>.<lang>.mp4` next to it, with lang one of `en`, `tw`, `ga`, `ee` or `fat`.
If the speech runs longer than the video, it holds the last frame.

- **English:** [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (Apache 2.0), voice `af_heart`.
  The two model files (about 120 MB) come from the kokoro-onnx `model-files-v1.0` release.
- **Twi, Ga, Ewe, Fante:** [Africa TTS](https://huggingface.co/AfriSpeech/africa-tts) by AfriSpeech.
  It's **CC BY-NC 4.0**: non-commercial use only, with credit, which the guides show. It downloads
  about 440 MB on first use.

Only the English scripts are final. The Twi, Ga, Ewe and Fante scripts are drafts (`"draft": true`
in `narration.json`). When a native speaker has corrected a script, edit it, set `draft` to false,
and run the voices again for that language.

```bash
python3 -m venv /tmp/tts && /tmp/tts/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
```

```bash
/tmp/tts/bin/pip install africa-tts kokoro-onnx soundfile imageio-ffmpeg
```

```bash
FFMPEG=$(/tmp/tts/bin/python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())") /tmp/tts/bin/python tools/demo/voice.py --kokoro <kokoro folder> --langs tw
```

`--only credit,stock` limits it to some guides, and `--langs` to some languages.
