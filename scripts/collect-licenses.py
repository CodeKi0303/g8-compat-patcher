"""Collect notices for the exact installed runtime used by a Windows build."""
import argparse
import hashlib
import importlib.metadata
import json
import shutil
import ssl
import sys
import tkinter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = args.destination
    destination.mkdir(parents=True, exist_ok=False)
    runtime = Path(sys.base_prefix)
    tk = tkinter.Tk()
    tk.withdraw()
    tcl_version = str(tk.tk.call("info", "patchlevel"))
    tk_version = str(tk.tk.call("package", "require", "Tk"))
    tk_library = Path(str(tk.tk.call("set", "tk_library")))
    tk.destroy()
    if (tcl_version, tk_version) != ("8.6.15", "8.6.15"):
        raise ValueError("Review and add matching Tcl/Tk notices before packaging a different runtime version")
    package = importlib.metadata.distribution("pyinstaller")
    copying = next(package.locate_file(p) for p in package.files if str(p).endswith("licenses/COPYING.txt"))
    sources = {
        "Python-LICENSE.txt": runtime / "LICENSE.txt",
        "Python-third-party-licenses.html": runtime / "Doc/html/license.html",
        "Tcl-8.6.15-license.terms": root / "licenses/Tcl-8.6.15-license.terms",
        "Tk-8.6.15-license.terms": tk_library / "license.terms",
        "PyInstaller-COPYING.txt": copying,
        "Apache-2.0.txt": root / "licenses/Apache-2.0.txt",
    }
    records = []
    for name, source in sources.items():
        shutil.copyfile(source, destination / name)
        records.append({"file": name, "sha256": hashlib.sha256((destination / name).read_bytes()).hexdigest()})
    record = {"python": sys.version.split()[0], "pyinstaller": package.version,
              "tcl": tcl_version, "tk": tk_version, "openssl": ssl.OPENSSL_VERSION, "files": records}
    (destination / "runtime-notices.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
