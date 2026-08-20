#!/usr/bin/env python3
"""Run the building engine.

    python3 run.py                       open the page in a browser
    python3 run.py "a 6 storey office of 11000 m2 with a courtyard"

The first form needs a few packages; if they are missing this offers to put
them in a .venv inside this folder and start again, so nothing is installed
anywhere else on the machine. The second form needs nothing at all -- the
engine itself is standard library Python.

Set ANTHROPIC_API_KEY to have briefs read as prose rather than by keyword.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
VENV = os.path.join(HERE, ".venv")
NEEDS = ["fastapi", "uvicorn", "pydantic", "anthropic"]


def venv_python():
    if os.name == "nt":
        return os.path.join(VENV, "Scripts", "python.exe")
    return os.path.join(VENV, "bin", "python3")


def have(mods):
    for m in mods:
        try:
            __import__(m)
        except ImportError:
            return False
    return True


def setup_and_restart():
    """Make a .venv here, install what the page needs, and re-run."""
    py = venv_python()
    if not os.path.isfile(py):
        print("The page needs a few packages: fastapi, uvicorn, pydantic,\nhttpx and anthropic.")
        print("They can go in a folder called .venv inside this project, so")
        print("nothing else on your computer is touched.")
        try:
            answer = input("Set that up now? [Y/n] ").strip().lower()
        except EOFError:
            answer = "y"
        if answer not in ("", "y", "yes"):
            print("\nNothing installed. You can still use the engine without "
                  "any of this:")
            print('  python3 run.py "a 6 storey office of 11000 m2"')
            return 1
        print("\nMaking .venv ...")
        r = subprocess.run([sys.executable, "-m", "venv", VENV])
        if r.returncode or not os.path.isfile(py):
            print("\nCould not make a virtual environment. On Debian or Ubuntu "
                  "this usually means:\n  sudo apt install python3-venv",
                  file=sys.stderr)
            return 1
        print("Installing ...")
        r = subprocess.run([py, "-m", "pip", "install", "--quiet", "--upgrade",
                            "pip"])
        r = subprocess.run([py, "-m", "pip", "install", "--quiet", "-r",
                            os.path.join(HERE, "requirements.txt")])
        if r.returncode:
            print("\nInstall failed. Try it by hand:\n  %s -m pip install -r "
                  "requirements.txt" % py, file=sys.stderr)
            return 1
        print("Done.\n")
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.call([py, os.path.abspath(__file__)] + sys.argv[1:],
                           env=env)


def serve(port, open_browser=True):
    import uvicorn
    url = "http://127.0.0.1:%d" % port
    print("\n  The engine is running.")
    print("  Open %s in your browser." % url)
    print("  Press Control-C here to stop it.\n")
    if open_browser:
        try:
            import threading
            import webbrowser
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        except Exception:
            pass
    os.environ.setdefault("ARCHIAI_STORAGE", "local")
    os.environ.setdefault("ARCHIAI_LOCAL_ROOT", os.path.join(HERE, "output",
                                                             "generated"))
    uvicorn.run("archiai.service.app:app", host="127.0.0.1", port=port,
                log_level="warning")
    return 0


def main(argv):
    sys.path.insert(0, SRC)
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    port = 8080
    for f in list(flags):
        if f.startswith("--port="):
            port = int(f.split("=", 1)[1])
            flags.discard(f)

    if args or "--help" in flags or "-h" in flags:
        from archiai.__main__ import main as cli          # no dependencies
        return cli(argv)

    if not have(NEEDS):
        if os.path.abspath(sys.executable).startswith(os.path.abspath(VENV)):
            print("The packages are still missing inside .venv. Try:\n"
                  "  %s -m pip install -r requirements.txt" % venv_python(),
                  file=sys.stderr)
            return 1
        return setup_and_restart()
    return serve(port, "--no-browser" not in flags)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
