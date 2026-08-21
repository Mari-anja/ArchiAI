"""Settings that live in the project rather than in a terminal.

`export ANTHROPIC_API_KEY=...` lasts exactly as long as the window it was
typed in, which is a poor place to keep the one setting that decides whether
the engine can read a brief at all. A `.env` file beside run.py is read at
startup instead, so it is set once and stays set.

The environment still wins: anything already exported is left alone.
"""

import os

NAME = ".env"

# Which settings came out of the file, and which the file was not allowed to
# set because something had already exported them. An export that shadows the
# file is the one way this can go quietly wrong.
FROM_FILE = set()
SHADOWED = set()


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
    FROM_FILE.discard("ANTHROPIC_API_KEY")
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
        if not key:
            continue
        if key in os.environ:                   # a real export still wins
            if os.environ[key] != value:
                SHADOWED.add(key)
            continue
        os.environ[key] = value
        FROM_FILE.add(key)
        done.append(key)
    return done


def source(key):
    """Where a setting came from, in words a person can act on."""
    if key not in os.environ:
        return None
    if key in SHADOWED:
        return "an exported variable, which is overriding the .env file"
    if key in FROM_FILE:
        return "the .env file"
    return "an exported variable"
