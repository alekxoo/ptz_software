import os
import sys
import json
import certifi
from typing import Any, Dict
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

import httpx

from local_store import list_pending, load_file, delete, move_to_failed


def internet_available() -> bool:
    try:
        # lightweight connectivity check
        with httpx.Client(timeout=3.0) as client:
            r = client.get("https://www.gstatic.com/generate_204")
            return r.status_code in (200, 204)
    except Exception:
        return False


def mongo_client_from_env() -> MongoClient:
    mongo_uri = os.getenv("MongoDB_URI", "mongodb://localhost:27017")
    use_tls = ("mongodb.net" in mongo_uri) or mongo_uri.startswith("mongodb+srv")
    return MongoClient(
        mongo_uri,
        tls=use_tls,
        tlsCAFile=certifi.where() if use_tls else None,
        serverSelectionTimeoutMS=15000,
    )


def apply_to_mongo(db, collection: str, doc: Dict[str, Any]) -> None:
    if collection == "device_latest":
        # Upsert by device_id for latest snapshot
        device_id = doc.get("device_id")
        if not device_id:
            raise ValueError("device_latest missing device_id")
        db[collection].update_one({"device_id": device_id}, {"$set": doc}, upsert=True)
    else:
        db[collection].insert_one(doc)


def main() -> int:
    load_dotenv()

    if not internet_available():
        print("[sync] No internet connectivity; will retry later.")
        return 2

    try:
        client = mongo_client_from_env()
        client.admin.command("ping")
    except Exception as e:
        print(f"[sync] Mongo not reachable: {e}")
        return 3

    dbname = os.getenv("MongoDB_DB", "monitoring_system")
    db = client[dbname]

    files = list_pending()
    if not files:
        print("[sync] No pending offline documents.")
        return 0

    success = 0
    failed = 0
    for path in files:
        try:
            payload = load_file(path)
            collection = payload.get("_collection")
            if not collection:
                raise ValueError("Missing _collection in payload")
            doc = payload.get("doc")
            if not isinstance(doc, dict):
                raise ValueError("Invalid doc in payload")
            apply_to_mongo(db, collection, doc)
            delete(path)
            success += 1
        except (PyMongoError, Exception) as e:
            move_to_failed(path)
            failed += 1
            print(f"[sync] Failed to sync {path}: {e}")

    print(f"[sync] Completed. success={success} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

