# Security & Privacy

## Privacy — how the microphone is used

Clap to Open listens to your microphone **only to detect claps**, and it does so
**entirely on your machine, in real time**:

- Audio is analysed in memory by the local `clap-detector` library and discarded.
- **Nothing is recorded to disk. Nothing is sent over the network.** There is no
  cloud, no telemetry, no analytics.
- The listener is **off by default** and is started by you (a toggle in the panel
  or `clap ctl on`). It is not auto-enabled at install.
- It's open source — you can read exactly what the listener does in
  [`src/clap_to_open/listener.py`](src/clap_to_open/listener.py).

## Reporting a vulnerability

Please report security issues privately via
[GitHub Security Advisories](https://github.com/Forrest404/clap-to-open/security/advisories/new)
rather than a public issue. I'll respond as soon as I can.
