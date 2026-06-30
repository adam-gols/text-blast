# Text Blast — Setup Guide

Use this when setting up on a **new Mac** (clone or download from GitHub).

## Quick start

```bash
git clone https://github.com/adam-gols/text-blast.git
cd text-blast
chmod +x run.sh
./run.sh
```

**Always use `./run.sh`** — not plain `python3 text_blast_app.py`.

---

## "Tk is deprecated" warning

macOS may print:

> DEPRECATION WARNING: The system version of Tk is deprecated...

**This is not an error** — it means that Python is using Apple's old built-in Tk. The app should still work. `run.sh` silences this warning automatically.

For best results (modern UI, no warning), install **Python from python.org** (includes Tcl/Tk 8.6), not the system `/usr/bin/python3`.

---

## Why the UI doesn't show on a new Mac

Text Blast needs **Tkinter** for its window. Many Macs only have Homebrew `python3`, which **does not include Tkinter** — the app exits silently or with an error and no window appears.

`run.sh` finds a Python that has Tkinter and installs dependencies automatically.

---

## If `./run.sh` says no Tkinter found

1. Download **Python 3.12** from https://www.python.org/downloads/macos/
2. Run the installer (default options are fine)
3. In Terminal:

```bash
cd text-blast
./run.sh
```

---

## Build a standalone app (copy to other Macs)

On a Mac that already runs Text Blast:

```bash
chmod +x build_text_blast.sh
./build_text_blast.sh
```

Copy **`dist/TextBlast.app`** to the other Mac — no Python install needed there.

First launch on the new Mac: right-click **TextBlast.app** → **Open**.

---

## Permissions

- **Automation** → allow Messages for Terminal/Python
- **Accessibility** → only needed for CC group texts

## Airtable

Paste your `pat...` token in the app header and click **Save**.
