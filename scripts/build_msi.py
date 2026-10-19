"""Build a per-user MSI installer for MD Viewer (PyInstaller one-folder build + WiX).

Run from anywhere:  .venv\\Scripts\\python scripts\\build_msi.py [--skip-exe]
Output:             dist\\MDViewer-<version>-x64.msi
Requires:           the .NET SDK and the repo-local WiX tool (`dotnet tool restore`).
"""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "dist" / "MDViewer"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-exe", action="store_true", help="reuse the existing dist\\MDViewer folder")
    args = parser.parse_args()

    if not args.skip_exe:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_exe.py")], cwd=ROOT)
        if result.returncode != 0:
            return result.returncode
    if not (APP_DIR / "MDViewer.exe").is_file():
        print(f"{APP_DIR}\\MDViewer.exe not found; run without --skip-exe.", file=sys.stderr)
        return 1

    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    msi = ROOT / "dist" / f"MDViewer-{version}-x64.msi"

    restore = subprocess.run(["dotnet", "tool", "restore"], cwd=ROOT)
    if restore.returncode != 0:
        return restore.returncode
    cmd = [
        "dotnet", "tool", "run", "wix", "build",
        str(ROOT / "installer" / "MDViewer.wxs"),
        "-arch", "x64",
        "-d", f"SourceDir={APP_DIR}",
        "-d", f"Version={version}",
        "-d", f"IconPath={ROOT / 'assets' / 'mdviewer.ico'}",
        "-o", str(msi),
    ]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode
    print(f"\nBuilt {msi} ({msi.stat().st_size / 1_048_576:.0f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
