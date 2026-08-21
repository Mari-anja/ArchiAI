"""Settings that live in the project rather than in a terminal.

`export ANTHROPIC_API_KEY=...` lasts exactly as long as the window it was
typed in, which is a poor place to keep the one setting that decides whether
the engine can read a brief at all. A `.env` file beside run.py is read at
startup instead, so it is set once and stays set.

The environment still wins: anything already exported is left alone.
"""

import os

NAME = ".env"


def find(start=None):
    """The .env beside run.py, whatever directory the engine was started in."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.dirname(here)                # src/archiai -> src -> project
    for d in (start, root, os.getcwd()):
        if not d:
            continue
        p = os.path.join(d, NAME)
        if os.path.isfile(p):
            return p
    return None


def load(path=None):
    """Read KEY=value lines into the environment. Returns what it set."""
    path = path or find()
    if not path:
        return []
    done = []
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key or key in os.environ:        # a real export still wins
            continue
        os.environ[key] = value
        done.append(key)
    return done
