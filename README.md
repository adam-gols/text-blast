# Text Blast

Standalone macOS app for sending personalized texts to coaches and staff via **iMessage** (with SMS fallback). Messages go out through your Mac's **Messages** app — not through Twilio or any SMS API.

## Requirements

- macOS with the **Messages** app signed in to iMessage/SMS
- Python 3.11+ with **Tkinter** (e.g. `/usr/local/bin/python3.12`)
- **Automation** permission for Messages (System Settings → Privacy & Security → Automation)
- Optional: **Accessibility** permission for Terminal/Python if using group CC texts

## Install

```bash
cd text-blast
python3.12 -m pip install -r requirements.txt
```

## Run

```bash
python3.12 text_blast_app.py
```

With an event pre-selected:

```bash
python3.12 text_blast_app.py --event "Your Event Name"
```

## Build macOS app (optional)

```bash
chmod +x build_text_blast.sh
./build_text_blast.sh
open dist/TextBlast.app
```

## Usage

1. **Airtable token** — paste in the header and click Save (stored in Keychain + `~/.sitetools/.env`)
2. **Pull contacts** — Event Staffing or Contractors by Pod, or paste manually
3. **Message template** — use variables like `{name}` (first name only), `{site}`, `{date}`, `{pod}`, etc.
4. **CC (optional)** — adds your CC number; tries a group text first, falls back to a separate copy if macOS blocks group creation
5. **Preview** → **Send All**

App state (contacts, template, filters, CC) auto-saves to `~/.sitetools/text_blast_state.json`.

## Template variables

| Variable | Meaning |
|---|---|
| `{name}` | First name |
| `{site}` | Venue/site (event staffing) |
| `{computer}` | Assigned computer |
| `{channel}` | Channel title |
| `{date}` | Stream date |
| `{pod}` | Pod (contractors) |
| `{region}` | Region (contractors) |

## Troubleshooting

| Issue | Fix |
|---|---|
| Sends fail with CC | Enable **Accessibility** for Terminal/Python, or rely on separate-copy fallback |
| No messages in Messages | Check Automation permission for Messages; keep Messages open while sending |
| Airtable pull fails | Save a valid `pat...` token in the header |

## License

Private / internal use — GOLS Game On Live Studio.
