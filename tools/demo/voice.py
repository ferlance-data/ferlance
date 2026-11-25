"""Give the guide videos a spoken narration in English, Twi, Ga, Ewe and Fante.

Reads frontend/src/lib/narration.json, speaks each script, and muxes it onto the silent video
recorded by record.mjs: frontend/public/assets/demo/<slug>.mp4 -> <slug>.<lang>.mp4.

Voices (both free, run on this machine):
  - English: Kokoro (Apache-2.0) via kokoro-onnx, voice af_heart.
  - Twi, Ga, Ewe, Fante: Africa TTS by AfriSpeech (CC-BY-NC-4.0: non-commercial use only).

usage: python voice.py --kokoro <dir with kokoro-v1.0.int8.onnx and voices-v1.0.bin> [--only start,credit] [--langs tw,ga]
needs: FFMPEG=<an ffmpeg with libx264 and aac>, pip install africa-tts kokoro-onnx soundfile
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "frontend/public/assets/demo"
NARRATION = ROOT / "frontend/src/lib/narration.json"
RATE = 24_000
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
LEAD, TAIL, PAUSE = 0.6, 0.8, 0.28  # seconds of quiet before, after, and between sentences
AFRICA_LANG = {"tw": "twi", "ga": "gaa", "ee": "ewe", "fat": "fat"}


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?:])\s+", text) if part.strip()]


class Voices:
    def __init__(self, kokoro_dir: Path):
        self.kokoro_dir = kokoro_dir
        self._kokoro = None
        self._africa = None

    def speak(self, text: str, lang: str) -> np.ndarray:
        pieces = []
        for sentence in sentences(text):
            pieces.append(self._one(sentence, lang))
            pieces.append(np.zeros(int(PAUSE * RATE), dtype=np.float32))
        return np.concatenate(pieces[:-1]) if pieces else np.zeros(0, dtype=np.float32)

    def _one(self, sentence: str, lang: str) -> np.ndarray:
        if lang == "en":
            if self._kokoro is None:
                from kokoro_onnx import Kokoro

                self._kokoro = Kokoro(str(self.kokoro_dir / "kokoro-v1.0.int8.onnx"), str(self.kokoro_dir / "voices-v1.0.bin"))
            samples, rate = self._kokoro.create(sentence, voice="af_heart", speed=1.0, lang="en-us")
            return _resample(np.asarray(samples, dtype=np.float32), rate)
        if self._africa is None:
            from africa_tts import AfricaTTS

            self._africa = AfricaTTS.load(download=True)
        audio = self._africa.generate(sentence, lang=AFRICA_LANG[lang])
        return np.asarray(audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio, dtype=np.float32).reshape(-1)


def _resample(samples: np.ndarray, rate: int) -> np.ndarray:
    if rate == RATE:
        return samples
    positions = np.linspace(0, len(samples) - 1, int(len(samples) * RATE / rate))
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.float32)


def duration(video: Path) -> float:
    probe = subprocess.run([FFMPEG, "-i", str(video)], capture_output=True, text=True).stderr
    hours, minutes, seconds = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe).groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def mux(video: Path, speech: np.ndarray, target: Path) -> float:
    """Lay the speech over the video; hold the last frame if the speech runs longer."""
    length = duration(video)
    spoken = LEAD + len(speech) / RATE + TAIL
    with tempfile.TemporaryDirectory() as work:
        wav = Path(work) / "speech.wav"
        sf.write(wav, np.concatenate([np.zeros(int(LEAD * RATE), dtype=np.float32), speech]), RATE)
        hold = max(0.0, spoken - length)
        video_args = (["-vf", f"tpad=stop_mode=clone:stop_duration={hold:.2f}", "-c:v", "libx264", "-profile:v", "main", "-crf", "30", "-preset", "slow", "-pix_fmt", "yuv420p"]
                      if hold else ["-c:v", "copy"])
        subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", str(video), "-i", str(wav), "-map", "0:v", "-map", "1:a", *video_args,
             "-af", f"loudnorm=I=-16:TP=-1.5,apad=whole_dur={max(length, spoken):.2f}", "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "44100",
             "-t", f"{max(length, spoken):.2f}", "-movflags", "+faststart", str(target)],
            check=True,
        )
    return max(length, spoken)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kokoro", type=Path, required=True)
    parser.add_argument("--only", default="")
    parser.add_argument("--langs", default="")
    args = parser.parse_args()
    data = json.loads(NARRATION.read_text(encoding="utf-8"))
    only = set(filter(None, args.only.split(",")))
    langs = [lang for lang in data["languages"] if not args.langs or lang in args.langs.split(",")]
    voices = Voices(args.kokoro)
    for slug, scripts in data["guides"].items():
        if only and slug not in only:
            continue
        for lang in langs:
            speech = voices.speak(scripts[lang], lang)
            target = DEMO / f"{slug}.{lang}.mp4"
            total = mux(DEMO / f"{slug}.mp4", speech, target)
            print(f"{slug}.{lang}: speech {len(speech) / RATE:.1f}s, video {total:.1f}s, {target.stat().st_size // 1024} KB", flush=True)


if __name__ == "__main__":
    main()
