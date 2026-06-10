"""Mic listener: on a clap-of-N, fire the boot sequence.

All tuning comes from ``config.json`` (:mod:`clap_to_open.config`) so the web
UI can change sensitivity, the clap count and the cooldown without touching
code — a service restart applies the new values.
"""
import subprocess
import sys
import time

from clapDetector import ClapDetector

from . import config, paths


def main():
    cfg = config.load()
    s = cfg["sensitivity"]
    trig = cfg["trigger"]
    clap_count = trig["clap_count"]
    cooldown = trig["cooldown_seconds"]

    # Use the PipeWire "default" device (-1): it buffers cleanly where direct
    # ALSA hw overflows and named-device enumeration is flaky.
    det = ClapDetector(
        inputDevice=s["input_device"],
        logLevel=20,
        initialVolumeThreshold=s["initial_volume_threshold"],
        resetTime=s["reset_time"],
    )
    det.initAudio()
    print(f"clap-to-open: listening for {clap_count}-claps…", flush=True)

    while True:
        result = det.run(
            thresholdBias=s["threshold_bias"],
            lowcut=s["lowcut"],
            highcut=s["highcut"],
            audioData=det.getAudio(),
        )
        if len(result) == clap_count:
            print(f"{clap_count} claps -> boot", flush=True)
            subprocess.Popen([sys.executable, "-m", "clap_to_open.boot"])
            time.sleep(cooldown)  # cooldown so the echo doesn't re-trigger
        time.sleep(1 / 60)


if __name__ == "__main__":
    main()
