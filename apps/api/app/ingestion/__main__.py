import argparse
import json

from sqlalchemy.orm import Session

from app.db import get_engine
from app.ingestion.service import MODELS, bulk_enqueue

parser = argparse.ArgumentParser(description="Queue ingestion for existing content")
parser.add_argument("command", choices=["enqueue"])
parser.add_argument("--all", action="store_true", required=True)
parser.add_argument("--reason", default="backfill", choices=["backfill", "manual"])
args = parser.parse_args()
with Session(get_engine()) as db:
    result = bulk_enqueue(db, list(MODELS), args.reason)
    db.commit()
    print(json.dumps(result))
