#!/bin/bash
# Launch Text Blast — finds a Python with Tkinter (required for the UI)

set -e
cd "$(dirname "$0")"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "Text Blast requires macOS (uses the Messages app to send texts)."
  exit 1
fi

PYTHON=""
for candidate in \
  /usr/local/bin/python3.12 \
  /usr/local/bin/python3.11 \
  /opt/homebrew/bin/python3.12 \
  /opt/homebrew/bin/python3.11 \
  python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import tkinter" 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo ""
  echo "Text Blast could not find Python with Tkinter (the UI toolkit)."
  echo ""
  echo "Fix: install Python from https://www.python.org/downloads/"
  echo "     (the python.org installer includes Tkinter — Homebrew Python often does not)"
  echo ""
  echo "Then run:  ./run.sh"
  exit 1
fi

echo "Using $PYTHON"
"$PYTHON" -m pip install -q -r requirements.txt
exec "$PYTHON" text_blast_app.py "$@"
