"""MD Viewer entry point: hands argv to mdviewer.app.main."""

import sys

from mdviewer.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
