# Third party notices

The project's MIT license covers its original patcher implementation and documentation. It does not license vendor firmware, third-party trademarks, or third-party runtime components under MIT.

## GameSir firmware

GameSir firmware is not included in the repository, Python package, or patcher executable. The user obtains the original directly from the GameSir server or supplies a local copy. The patcher checks the exact source digest before creating a modified copy locally. Public profile definitions contain offsets, replacement bytes, and digests rather than complete firmware images or original-byte dumps.

This project has not obtained a grant to redistribute GameSir firmware. Availability at a download URL does not establish such permission. Do not add original or generated firmware to source distributions, release assets, or CI artifacts.

## Python runtime and Windows packaging

The Python source package has no third-party runtime package dependencies. It uses Python's standard library, including Tkinter for the optional graphical interface.

A packaged Windows executable includes a Python runtime and the runtime libraries selected by the packager, including Tcl/Tk for the GUI. Their original license notices are supplied with the Windows distribution under `licenses/`; keep that directory with the executable when redistributing the package.

PyInstaller is used to build the Windows executable. Its licensing exception permits distributing the generated application under its own license while respecting the licenses of bundled dependencies. The exception does not relicense Python, Tcl/Tk, or other bundled components. See [PyInstaller's licensing explanation](https://pyinstaller.org/en/stable/license.html) and the license texts supplied with the build tools.

## Product identifiers

GameSir, Razer, Kishi, Xbox, Sony, and PlayStation names and identifiers describe compatibility behavior. Their use does not imply affiliation, certification, or endorsement. This project's license grants no trademark rights.
