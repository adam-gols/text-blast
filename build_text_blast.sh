#!/bin/bash
# Build TextBlast.app — standalone macOS text messaging app

echo "Building TextBlast.app..."

PYTHON=""
for candidate in /usr/local/bin/python3.12 /opt/homebrew/bin/python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import tkinter" 2>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "No Python with Tkinter found. Install Python 3.11+ with Tk support."
    exit 1
fi

echo "Using $PYTHON"

"$PYTHON" -m pip install pyinstaller requests python-dotenv keyring --quiet

rm -rf build dist/TextBlast.app dist/TextBlast

"$PYTHON" -m PyInstaller TextBlast.spec -y

if [ -d "dist/TextBlast.app" ]; then
    echo ""
    echo "Build complete: dist/TextBlast.app"
    echo ""
    echo "To install:"
    echo "  cp -r dist/TextBlast.app /Applications/"
    echo "  First launch: right-click -> Open"
else
    echo "Build failed — check errors above"
    exit 1
fi
