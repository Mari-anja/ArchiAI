#!/usr/bin/env python3
"""Run the building engine.

    python3 run.py                       open the page in a browser
    python3 run.py --check               test the brief reader, loudly
    python3 run.py "a 6 storey office of 11000 m2 with a courtyard"

The first form needs a few packages; if they are missing this offers to put
them in a .venv inside this folder and start again, so nothing is installed
anywhere else on the machine. The second form needs nothing at all -- the
engine itself is standard library Python.

Put ANTHROPIC_API_KEY in a file called .env beside this one to have briefs
read as prose rather than by keyword. An exported variable works too, but
only in the terminal it was typed in.
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


CHECK_BRIEF = ("A monolithic block cut through by a tall planted void that "
               "opens out as it rises, dense below and light at the top.")


def check(brief):
    """Make one real call to the brief reader and say exactly what happened.

    A feature that quietly degrades is indistinguishable from a broken one,
    so there has to be a way to ask it directly."""
    import json
    from archiai.engine import interpret as IN

    def say(*a):
        print(*a)
        sys.stdout.flush()
    say("\n  Brief:\n    %s\n" % brief)
    where = IN.credentials()
    say("  Key: %s" % (("found in the " + where) if where
                       else "NOT FOUND -- put ANTHROPIC_API_KEY in .env"))
    if not where:
        return 2
    fp = IN.fingerprint()
    if fp:
        say("  Looks like: %s  (%d characters)" % (fp["shown"], fp["length"]))
        for n in fp["notes"]:
            say("     ! it %s" % n)
    say("  Model: %s" % IN.MODEL)
    say("  Calling ...\n")
    try:
        data = IN.read(brief)
    except Exception as e:
        say("  IT FAILED, and this is why:\n    %s: %s\n"
            % (type(e).__name__, e))
        if "authentication" in str(e) or "401" in str(e):
            say("  That is Anthropic rejecting the key itself, not a bug\n"
                "  here. Make a fresh one at console.anthropic.com under\n"
                "  API Keys, then put it in .env, all on one line:\n"
                "      echo 'ANTHROPIC_API_KEY=sk-ant-...' > %s\n"
                % os.path.join(HERE, ".env"))
        return 1
    say(json.dumps(data, indent=2, sort_keys=True))
    spec = IN.to_spec(data, brief)
    say("\n  Which becomes: %s -- %d storey %s, %s"
        % (spec.name, spec.storeys, spec.use, spec.shape))
    for a in spec.assumptions:
        say("    * %s" % a)
    say("\n  The reader works.\n")
    return 0


def free_port(port, tries=12):
    """The port asked for, or the next one nobody is sitting on.

    An engine left running in a terminal that has since been closed is the
    normal case, not an error worth stopping for."""
    import socket
    for i in range(tries):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port + i))
            return port + i
        except OSError:
            continue
        finally:
            s.close()
    return port


def serve(port, open_browser=True):
    import uvicorn
    from archiai.engine import interpret as IN
    asked, port = port, free_port(port)
    if port != asked:
        print("\n  Something is already using port %d -- probably an engine "
              "still\n  running in another terminal. Using %d instead."
              % (asked, port))
    url = "http://127.0.0.1:%d" % port
    print("\n  The engine is running.")
    if IN.available():
        print("  Briefs will be read as prose.")
    else:
        print("  No Anthropic key found, so briefs are read by keyword only.")
        print("  To fix it, once and for good:")
        print("      echo 'ANTHROPIC_API_KEY=sk-ant-...' > %s"
              % os.path.join(HERE, ".env"))
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
    from archiai import env as ENV
    ENV.load()
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    port = 8080
    for f in list(flags):
        if f.startswith("--port="):
            port = int(f.split("=", 1)[1])
            flags.discard(f)

    # Anything that needs packages has to be running inside .venv first,
    # or it reports the packages missing while they sit installed next door.
    def ready(mods):
        if have(mods):
            return None
        if os.path.abspath(sys.executable).startswith(os.path.abspath(VENV)):
            print("The packages are still missing inside .venv. Try:\n"
                  "  %s -m pip install -r requirements.txt" % venv_python(),
                  file=sys.stderr)
            return 1
        return setup_and_restart()

    if "--check" in flags:
        stop = ready(["anthropic"])
        return stop if stop is not None else check(" ".join(args) or CHECK_BRIEF)

    if args or "--help" in flags or "-h" in flags:
        from archiai.__main__ import main as cli          # no dependencies
        return cli(argv)

    stop = ready(NEEDS)
    return stop if stop is not None else serve(port, "--no-browser" not in flags)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
