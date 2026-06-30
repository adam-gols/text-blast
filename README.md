# Text Blast

Standalone **macOS** app for sending personalized texts via **iMessage** (with SMS fallback). Messages go out through your Mac's **Messages** app.

## Quick start

```bash
git clone https://github.com/adam-gols/text-blast.git
cd text-blast
chmod +x run.sh
./run.sh
```

> **Important:** Use `./run.sh` to launch. Plain `python3` on many Macs does **not** include Tkinter, so **no UI window will appear**.

See **[SETUP.md](SETUP.md)** for full install instructions.

## Another Mac (easiest)

Build once on a Mac that already works, then copy the app — **no Python needed** on the other machine:

```bash
./build_text_blast.sh
# Copy dist/TextBlast.app to the other Mac (AirDrop, Drive, etc.)
# First launch: right-click TextBlast.app → Open
```

## Requirements

- macOS with **Messages** signed in to iMessage/SMS
- Python 3.11+ **with Tkinter** ([python.org](https://www.python.org/downloads/) recommended)
- **Automation** permission for Messages
- Optional: **Accessibility** for CC group texts

## Project files

| File | Purpose |
|---|---|
| `run.sh` | **Start here** — finds Python with Tkinter, installs deps, opens UI |
| `text_blast_app.py` | Tkinter UI |
| `text_blast_lib.py` | Airtable fetch, templates, AppleScript send |
| `launcher.py` | PyInstaller entry point for `TextBlast.app` |
| `build_text_blast.sh` | Build standalone macOS app |
| `SETUP.md` | Detailed setup & troubleshooting |

## Usage

1. Save your **Airtable token** in the header
2. **Pull contacts** (Event Staffing or Contractors by Pod) or paste manually
3. Write a **message template** — `{name}` = first name, `{site}`, `{date}`, `{pod}`, etc.
4. Optional **CC** number for group/separate-copy sends
5. **Preview** → **Send All**

State auto-saves to `~/.sitetools/text_blast_state.json`.

## Build macOS app

```bash
chmod +x build_text_blast.sh
./build_text_blast.sh
open dist/TextBlast.app
```

## License

Private / internal use — GOLS Game On Live Studio.
