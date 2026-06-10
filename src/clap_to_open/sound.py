"""Startup-sound playback in three modes: ``file``, ``url`` or ``off``.

- **file** — play a local audio file offline via ``paplay`` (PipeWire/PulseAudio)
  with ``ffplay`` as a fallback. This is the default and needs no network.
- **url** — open the URL in a dedicated browser app-window with autoplay forced
  (a separate profile so the autoplay flag actually applies). Preserves the old
  YouTube-clip behaviour.
- **off** — silent boot.
"""
import os
import shutil
import subprocess

from . import paths

# Compressed formats libsndfile/paplay can't reliably decode everywhere — play
# these with ffplay, which handles them universally. Anything else (wav, ogg,
# flac, opus) goes to paplay first.
_FFPLAY_FORMATS = {".mp3", ".m4a", ".aac", ".wma", ".mp4"}


def _paplay(path):
    subprocess.Popen(["paplay", path])


def _ffplay(path):
    subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])


def _play_file(path):
    path = paths.resolve(path)
    if not path:
        return
    if not os.path.exists(path):
        print(f"clap-to-open: sound file not found: {path}", flush=True)
        return
    ext = os.path.splitext(path)[1].lower()
    # Pick the preferred player order for this format, then use whichever exists.
    order = (["ffplay", "paplay"] if ext in _FFPLAY_FORMATS
             else ["paplay", "ffplay"])
    players = {"paplay": _paplay, "ffplay": _ffplay}
    for name in order:
        if shutil.which(name):
            players[name](path)
            return
    print("clap-to-open: no audio player (paplay/ffplay) found", flush=True)


def _play_url(url):
    if not url:
        return
    browser = (shutil.which("brave-browser") or shutil.which("brave")
               or shutil.which("google-chrome") or shutil.which("chromium"))
    if not browser:
        print("clap-to-open: no Chromium-based browser found for URL sound",
              flush=True)
        return
    # Dedicated profile so the autoplay flag is honoured (flags are ignored when
    # attaching to an already-running browser instance).
    subprocess.Popen([
        browser,
        f"--user-data-dir={paths.BRAVE_SOUND_PROFILE}",
        f"--app={url}",
        "--class=clapsound",
        "--autoplay-policy=no-user-gesture-required",
        "--no-first-run", "--no-default-browser-check",
    ])


def play(cfg):
    """Play the startup sound according to ``cfg['sound']``."""
    snd = cfg.get("sound", {})
    mode = snd.get("mode", "off")
    if mode == "file":
        _play_file(snd.get("file"))
    elif mode == "url":
        _play_url(snd.get("url"))
    # mode == "off": do nothing
