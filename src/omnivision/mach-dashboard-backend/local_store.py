import os
import json
import uuid
import threading
from datetime import datetime
from typing import Any, Dict, Optional

_lock = threading.Lock()


def _default_queue_dir() -> str:
    return os.getenv(
        "OFFLINE_QUEUE_DIR",
        os.path.join(os.path.dirname(__file__), "offline_queue"),
    )


def enqueue(collection: str, doc: Dict[str, Any], queue_dir: Optional[str] = None) -> str:
    """Persist a document to a per-collection queue as an individual JSON file.

    - Files are named by epoch ms and a uuid to preserve order and uniqueness.
    - Returns the file path written.
    """
    qdir = queue_dir or _default_queue_dir()
    cdir = os.path.join(qdir, collection)
    os.makedirs(cdir, exist_ok=True)

    # ensure JSON-serializable types
    def _default(o: Any):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Type not serializable: {type(o)}")

    fname = f"{int(datetime.utcnow().timestamp()*1000)}_{uuid.uuid4().hex}.json"
    fpath = os.path.join(cdir, fname)
    payload = {"_collection": collection, "doc": doc}

    with _lock:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=_default)
    return fpath


def list_pending(collection: Optional[str] = None, queue_dir: Optional[str] = None) -> list[str]:
    qdir = queue_dir or _default_queue_dir()
    paths: list[str] = []
    if collection:
        cdir = os.path.join(qdir, collection)
        if os.path.isdir(cdir):
            for name in sorted(os.listdir(cdir)):
                if name.endswith(".json"):
                    paths.append(os.path.join(cdir, name))
        return paths

    # all collections
    if not os.path.isdir(qdir):
        return []
    for coll in sorted(os.listdir(qdir)):
        cdir = os.path.join(qdir, coll)
        if not os.path.isdir(cdir):
            continue
        for name in sorted(os.listdir(cdir)):
            if name.endswith(".json"):
                paths.append(os.path.join(cdir, name))
    return paths


def load_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def move_to_failed(path: str, queue_dir: Optional[str] = None) -> str:
    qdir = queue_dir or _default_queue_dir()
    rel = os.path.relpath(path, qdir)
    failed_path = os.path.join(qdir, "failed", rel)
    os.makedirs(os.path.dirname(failed_path), exist_ok=True)
    os.replace(path, failed_path)
    return failed_path


def delete(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

