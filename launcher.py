#!/usr/bin/env python3
"""PyInstaller entry point — prevents fork issues in .app bundles on macOS."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from text_blast_app import main
    main()
