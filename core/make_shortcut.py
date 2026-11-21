"""Puts her on the desktop.

One icon, her name, her face. Double-click and she opens — no ULTRON, no boot
screen, nothing in between.

WHY THIS IS A SCRIPT AND NOT A SHIPPED .LNK
    A shortcut file baked on somebody else's machine points at that machine's
    paths. The one thing that has to be worked out here is where Python
    actually is, and that is only knowable where she is being installed.

WHAT IT DOES ON WINDOWS
    Writes a real .lnk through PowerShell (present on every Windows since 7),
    pointing at pythonw.exe — the windowless Python — with app.py as its
    argument, her folder as the working directory and her face as the icon.
    pythonw matters: pointed at python.exe, double-clicking her opens a black
    console first, which is the least romantic possible entrance.

    Run it with --start-menu to put her there instead of the desktop.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parent
ROOT = CORE.parent
APP  = CORE / "app.py"
ICON = ROOT / "assets" / "mikasa.ico"


def _pythonw() -> str:
    """The windowless interpreter beside this one, if it exists.

    sys.executable may be python.exe or pythonw.exe depending on how this
    script was started, and on a venv there may be only one of them.
    """
    exe = Path(sys.executable)
    if os.name != "nt":
        return str(exe)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.exists() else exe)


def _ps_quote(p: str) -> str:
    return "'" + str(p).replace("'", "''") + "'"


def make_windows_shortcut(start_menu: bool = False) -> tuple[bool, str]:
    pyw = _pythonw()
    if start_menu:
        target_dir = ("[Environment]::GetFolderPath("
                      "'Programs')")
    else:
        target_dir = ("[Environment]::GetFolderPath("
                      "'Desktop')")

    ps = f"""
$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
$dest = {target_dir}
$lnk = Join-Path $dest 'Mikasa.lnk'
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = {_ps_quote(pyw)}
$s.Arguments = {_ps_quote('"' + str(APP) + '"')}
$s.WorkingDirectory = {_ps_quote(str(ROOT))}
$s.Description = 'Mikasa'
$s.WindowStyle = 1
{('$s.IconLocation = ' + _ps_quote(str(ICON) + ',0')) if ICON.exists() else ''}
$s.Save()
Write-Output $lnk
"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=40)
        if out.returncode != 0:
            return False, (out.stderr or out.stdout or "powershell failed").strip()
        return True, (out.stdout or "").strip() or "created"
    except FileNotFoundError:
        return False, "powershell was not found"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    start_menu = "--start-menu" in sys.argv
    where = "Start Menu" if start_menu else "Desktop"

    if os.name != "nt":
        print(f"This machine is not Windows, so there is no {where} shortcut "
              f"to make.\nStart her with:  python3 {APP}")
        return 0

    ok, detail = make_windows_shortcut(start_menu)
    if ok:
        print(f"Mikasa is on the {where}.")
        print(f"  {detail}")
        print("Double-click it. ULTRON does not need to be running.")
        return 0
    print("Could not create the shortcut.")
    print(f"  {detail}")
    print(f"\nMikasa.bat does the same thing — double-click {ROOT / 'mikasa.bat'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
