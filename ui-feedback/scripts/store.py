"""Durable feedback store.

Everything the review loop knows lives in one JSON file inside the project
(`.uifeedback/feedback.json`) with PNG sidecars in `.uifeedback/shots/`.

A plain file is deliberate: the server process, the CLI and the Claude Code
hook are three separate processes that must agree on state, and the user wants
to see unfinished items days later. An in-memory session would lose all of
that. Writes are atomic (tmp + os.replace) and serialised with an advisory
lock so a hook firing mid-request can never read a half-written file.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl  # POSIX only; Windows falls back to atomic-replace alone.
except ImportError:  # pragma: no cover
    fcntl = None

SCHEMA_VERSION = 1

# The status ladder. `open` is a draft the user is still holding; `sent` is the
# handoff to the agent; `in_progress`/`done`/`wont_fix` are written by the agent
# as it works, which is what makes the rail show progress live.
STATUSES = ("open", "sent", "in_progress", "done", "wont_fix")
ACTIVE_STATUSES = ("open", "sent", "in_progress")
CLOSED_STATUSES = ("done", "wont_fix")
KINDS = ("bug", "change", "idea", "question")

DIR_NAME = ".uifeedback"
FILE_NAME = "feedback.json"
SHOTS_DIR = "shots"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, root: str | os.PathLike):
        self.dir = Path(root)
        self.path = self.dir / FILE_NAME
        self.shots = self.dir / SHOTS_DIR
        self.lock_path = self.dir / ".lock"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.shots.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- locking

    @contextmanager
    def _locked(self):
        if fcntl is None:
            yield
            return
        with open(self.lock_path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ------------------------------------------------------------------- i/o

    def _blank(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "project": self.dir.parent.name,
            "created_at": now_iso(),
            "items": [],
        }

    def read(self) -> dict:
        """Read without locking - fine for display paths, which tolerate a
        stale read far better than they tolerate blocking on a busy lock."""
        if not self.path.exists():
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return self._blank()
        data.setdefault("items", [])
        data.setdefault("version", SCHEMA_VERSION)
        return data

    def _write(self, data: dict) -> None:
        data["updated_at"] = now_iso()
        fd, tmp = tempfile.mkstemp(dir=str(self.dir), prefix=".feedback-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    @contextmanager
    def mutate(self):
        """Read-modify-write under the lock. Yields the whole document."""
        with self._locked():
            data = self.read()
            yield data
            self._write(data)

    # ----------------------------------------------------------------- items

    def items(self, status: str | None = None, route: str | None = None) -> list[dict]:
        out = self.read()["items"]
        if status:
            wanted = {
                "active": set(ACTIVE_STATUSES),
                "closed": set(CLOSED_STATUSES),
                "all": set(STATUSES),
            }.get(status, {status})
            out = [i for i in out if i.get("status") in wanted]
        if route:
            out = [i for i in out if (i.get("target") or {}).get("route") == route]
        return out

    def get(self, item_id: str) -> dict | None:
        for item in self.read()["items"]:
            if item.get("id") == item_id:
                return item
        return None

    def _next_id(self, data: dict) -> str:
        highest = 0
        for item in data["items"]:
            m = re.match(r"fb-(\d+)$", str(item.get("id", "")))
            if m:
                highest = max(highest, int(m.group(1)))
        return f"fb-{highest + 1:04d}"

    def add(self, payload: dict) -> dict:
        """Create an item. Unknown keys are kept - the overlay may capture more
        context than this version of the store knows how to name, and dropping
        it would silently lose evidence the user gathered."""
        with self.mutate() as data:
            item = dict(payload)
            item["id"] = self._next_id(data)
            item["created_at"] = now_iso()
            item["updated_at"] = item["created_at"]
            item.setdefault("status", "open")
            item.setdefault("kind", "change")
            item.setdefault("body", "")
            item.setdefault("target", {})
            item.setdefault("thread", [])
            item.setdefault("screenshot", None)
            item.setdefault("delivered_at", None)
            item.setdefault("resolution", None)
            if not item.get("title"):
                item["title"] = _title_from(item["body"]) or "(no description)"
            if item["status"] not in STATUSES:
                item["status"] = "open"
            if item["kind"] not in KINDS:
                item["kind"] = "change"
            data["items"].append(item)
            return item

    def update(self, item_id: str, changes: dict) -> dict | None:
        with self.mutate() as data:
            for item in data["items"]:
                if item.get("id") != item_id:
                    continue
                for key, value in changes.items():
                    if key in ("id", "created_at"):
                        continue
                    if key == "status" and value not in STATUSES:
                        continue
                    item[key] = value
                item["updated_at"] = now_iso()
                return item
        return None

    def delete(self, item_id: str) -> tuple[bool, str]:
        """Drop a draft. Only `open` items can go: once something has been sent
        it is part of the record of what was asked for, and quietly erasing it
        would leave the agent working on an item the list no longer admits to."""
        with self.mutate() as data:
            for idx, item in enumerate(data["items"]):
                if item.get("id") != item_id:
                    continue
                if item.get("status") != "open":
                    return False, "already sent - close it as done or won't fix instead"
                data["items"].pop(idx)
                return True, ""
        return False, "not found"

    def append_note(self, item_id: str, role: str, text: str) -> dict | None:
        """Append to an item's thread. The thread is how a 'done' carries its
        explanation, so the user reading the rail later sees what was changed
        and not just that something was."""
        with self.mutate() as data:
            for item in data["items"]:
                if item.get("id") != item_id:
                    continue
                item.setdefault("thread", []).append(
                    {"role": role, "at": now_iso(), "text": text}
                )
                item["updated_at"] = now_iso()
                return item
        return None

    def send(self, ids: list[str] | None = None) -> list[dict]:
        """Promote drafts to `sent`. Returns what moved, so the caller can tell
        the user how many items were handed over."""
        moved: list[dict] = []
        with self.mutate() as data:
            for item in data["items"]:
                if ids is not None and item.get("id") not in ids:
                    continue
                if item.get("status") != "open":
                    continue
                item["status"] = "sent"
                item["sent_at"] = now_iso()
                item["updated_at"] = item["sent_at"]
                item["delivered_at"] = None
                moved.append(item)
        return moved

    def take_undelivered(self) -> list[dict]:
        """Claim every item that is waiting for the agent and stamp it as
        delivered in the same locked write.

        Claim-and-stamp has to be one operation. If the hook read the pending
        list and stamped it afterwards, a Stop hook could hand the same batch
        back on every turn and the session would never be able to end.
        """
        claimed: list[dict] = []
        with self.mutate() as data:
            for item in data["items"]:
                if item.get("status") == "sent" and not item.get("delivered_at"):
                    item["delivered_at"] = now_iso()
                    claimed.append(json.loads(json.dumps(item)))
        return claimed

    def counts(self) -> dict:
        counts = {s: 0 for s in STATUSES}
        for item in self.read()["items"]:
            status = item.get("status")
            if status in counts:
                counts[status] += 1
        counts["undelivered"] = sum(
            1
            for i in self.read()["items"]
            if i.get("status") == "sent" and not i.get("delivered_at")
        )
        return counts

    # ------------------------------------------------------------ screenshots

    def save_shot(self, item_id: str, raw: bytes) -> str:
        rel = f"{SHOTS_DIR}/{item_id}.png"
        (self.dir / rel).write_bytes(raw)
        return rel

    def shot_path(self, rel: str) -> Path | None:
        candidate = (self.dir / rel).resolve()
        if not str(candidate).startswith(str(self.dir.resolve())):
            return None
        return candidate if candidate.exists() else None


def _title_from(body: str) -> str:
    first = (body or "").strip().splitlines()[0] if (body or "").strip() else ""
    first = re.sub(r"\s+", " ", first).strip()
    return first[:80] + ("..." if len(first) > 80 else "")


def find_project_root(start: str | os.PathLike | None = None) -> Path:
    """Walk up for a project marker so the store lands at the repo root no
    matter which subdirectory the server was started from."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / DIR_NAME).is_dir() or (candidate / ".git").exists():
            return candidate
    return here


# --------------------------------------------------------------- live servers
#
# The hook resolves a ledger by walking up from the session's cwd, which only
# finds it when the session happens to run inside the reviewed project. A
# session started anywhere else - a home directory, a sibling checkout, a tool
# repo the reviewer keeps open - walks up, finds no ledger, and exits silently
# while the reviewer watches their sent item sit there. That silence is the
# whole "hooks don't work" symptom, and hand-pinning the path in a wrapper
# script is how people have been working around it.
#
# So a serving process records itself here, and the hook can ask "what is
# actually being reviewed right now?" instead of only "what is under my cwd?".
# The registry is a cache of live processes, never a source of truth about
# feedback: every entry is re-verified (pid alive, port listening, ledger still
# on disk) before it is trusted, and pruned when it is not.

STATE_DIR = Path(
    os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
) / "uifb"
REGISTRY = STATE_DIR / "servers.json"


def _registry_read() -> dict:
    try:
        with open(REGISTRY, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _registry_write(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(STATE_DIR), prefix=".servers-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, REGISTRY)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _port_listening(port: int) -> bool:
    import socket

    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", int(port))) == 0


def _alive(entry: dict) -> bool:
    """A registry entry is only worth trusting if the process is still there,
    the port still answers, and the ledger it named still exists."""
    pid = entry.get("pid")
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    if not _port_listening(entry.get("port") or 0):
        return False
    return (Path(entry.get("root", "")) / DIR_NAME / FILE_NAME).exists()


def register_server(root: str | os.PathLike, port: int, target: str) -> None:
    key = str(Path(root).resolve())
    data = {k: v for k, v in _registry_read().items() if _alive(v)}
    data[key] = {
        "root": key,
        "port": int(port),
        "target": target,
        "pid": os.getpid(),
        "started_at": now_iso(),
    }
    _registry_write(data)


def unregister_server(root: str | os.PathLike) -> None:
    key = str(Path(root).resolve())
    data = _registry_read()
    if data.pop(key, None) is not None:
        _registry_write(data)


def live_servers() -> list[dict]:
    """Every review server currently serving, stale entries pruned away."""
    data = _registry_read()
    live = {k: v for k, v in data.items() if _alive(v)}
    if len(live) != len(data):
        try:
            _registry_write(live)
        except OSError:
            pass  # a read-only state dir must never break delivery
    return list(live.values())
