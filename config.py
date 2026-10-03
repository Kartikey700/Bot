import os

# Works both locally (via .env) and on hosting (via env vars)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("8727594396:AAEKJ8zYRZdF9JWcd-BVm3pl4QzsFKbpJ7Q", "")
OWNER_ID = int(os.environ.get("8220326660", "0"))

DB_PATH = os.environ.get("DB_PATH", "data/escrow.db")

# Universal fee slabs
FEE_SLABS = [
    (1, 100, ("fixed", 10)),
    (101, 599, ("fixed", 20)),
    (600, 2000, ("percent", 3.5)),
    (2001, float("inf"), ("percent", 3.0)),
]

CURRENCY = "₹"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it to .env or environment variables.")
if not OWNER_ID:
    raise RuntimeError("OWNER_ID is not set. Add it to .env or environment variables.")
