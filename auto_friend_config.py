"""
auto_friend_config.py — Configuration for automatic friend request dispatcher.

Supports multiple servers mapped to different sender accounts.
Configurations can be defined via:
1. Primary In-Code Multi-Server Fleet Configuration (for Render/Cloud deployment)
2. Local `servers_config.json` file (overrides in local development)
"""
import os
import json
import base64
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_CONFIG_PATH = os.path.join(BASE_DIR, "servers_config.json")

# Master system switch
ENABLE_AUTO_FRIEND_SYSTEM = os.environ.get("ENABLE_AUTO_FRIEND", "true").lower() in ("true", "1", "yes")
NOTIFY_DM_ON_SUCCESS = True
NOTIFY_DM_ON_CAPTCHA = True

def _dec(v: str) -> str:
    """Decodes token if base64 encoded, or returns as-is."""
    if not v:
        return ""
    try:
        decoded = base64.b64decode(v.encode()).decode()
        # Only return decoded if it looks like a valid Discord token
        if "." in decoded and len(decoded) > 40:
            return decoded
    except Exception:
        pass
    return v

# ── Primary In-Code Multi-Server Fleet Configuration ──
# ── Batch 1 Fleet Configuration ──
BATCH_1_SERVERS = {
    "820056640417038356": {
        "server_name": "Due Diligence",
        "sender_token": _dec("TVRNeU16UXlOakF3TWpFd05USTNNRFF3TXcuR2lRR1JXLm9WTU8wamhqSVF4MmFOOXhwMUFMY1JTV29vLXo1RXN2RURCVVpr"),
        "sender_label": "talon.1977._",
        "enabled": True,
        "delay_seconds": 6.0,
    },

    "1433212223970345043": {
        "server_name": "DVLT Underground",
        "sender_token": _dec("TVRVMk16WTBORGt4T1RVeE1EUTNNRGMyTWcuR0prc3NmLlYzeHQzTkRTQlJYdlZ4SkF1NkJiVGZNUXFZdXBlOElIY0pPd3hN"),
        "sender_label": "themaster._5",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "1432925421145686028": {
        "server_name": "RJK Trades",
        "sender_token": _dec("TVRVMk16WTJPVGN6TXpjd05EY3pNamM0TncuR19tWDd1LjI4MkhSSk1reDFDQ2RUNXMyWDlmdE5TWGZ3SmhIWXM4SzFhMzlZ"),
        "sender_label": "official___rjktrades",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "563389318773604382": {
        "server_name": "Horizon Trading",
        "sender_token": _dec("TVRBeE1ERXdPRFl3TURRME16YzBNREl5TUEuR0lBaG9QLmRoQ1lzenFJbTlKeXBWOE5XazFIYTlBNlB4QXE0Y2RuWXJiU0hn"),
        "sender_label": "horizon.trading.",
        "enabled": True,
        "delay_seconds": 6.0,
    },
}

# ── Batch 2 Fleet Configuration ──
BATCH_2_SERVERS = {
    "804369780429291590": {
        "server_name": "DeepFuckingValue",
        "sender_token": _dec("TVRVMk1qa3dPRGt4TmpZd09EWTJNelU1TlEuRzlfcEEwLnA1dEpDYl9zMTNxZVBuVG4zY2VNSlhJRGt0VmZkM0pEbmVuWFpv"),
        "sender_label": "shiny.wind.up.bird",
        "enabled": True,
        "delay_seconds": 6.0,
    },

    "1330889066425749576": {
        "server_name": "PASE",
        "sender_token": _dec("TVRVMk1UWTVNalV3TXpBM01qTXhNek0yTlEuRzNSZUltLm5rZUN0VkRqeHFRZTE1M2VfUGhoUklrd0VybjRXNHhQenQ1QVNV"),
        "sender_label": "nicliu___",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "828801846277308426": {
        "server_name": "Mylol Trading Community",
        "sender_token": _dec("TVRVMk16WTNNelkwTURneE1qSTRNakEwT0EuR1owX3o1LlEzTEVaSDNaNEd5NnhyV1RDRXBERVlPeTdTLVhOVjE3b3ZuOHpV"),
        "sender_label": "seanlala._",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "1306399620217438309": {
        "server_name": "PAYTIENCE",
        "sender_token": _dec("TVRVMk1qa3lPVEExTkRVeE9UTTVORFF3TncuR1lMTllBLjdOR3UwOE00dFZ0SE14OG1jQUZ1eElmSlRXQjQxZ2JuNkl1QXI0"),
        "sender_label": "cooliam___",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "797916560714235946": {
        "server_name": "Juicy Tradez",
        "sender_token": _dec("TVRJME9ESTBNelkwTURJMk1qZzFOamMyTlEuR0ZwUHZFLnZfLWNOZXBzMzZHNnFVVzJRNnlDZzM3ZVN4RzhLblNDbHJfNWcw"),
        "sender_label": "xaviermastertrader",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "1334980338467733596": {
        "server_name": "Verified Wealth",
        "sender_token": _dec(""),
        "sender_label": "UNASSIGNED",
        "enabled": False,
        "delay_seconds": 6.0,
    },
    "808057094904217610": {
        "server_name": "PennyQueen",
        "sender_token": _dec("TnpnNU16UTROemczTlRVek9ESTRPRGMxLkdWci1jUi5lamlnNEwzX3B0bEtYNklsN3p2U1lWZF9wS2VESEFZQVg0RTVUbw=="),
        "sender_label": "ptbysr9767",
        "enabled": True,
        "delay_seconds": 6.0,
    },
}

# ── Dynamic Batch Selector ──
# Set SERVICE_BATCH="all" by default so a single runner handles both batches
SERVICE_BATCH = str(os.environ.get("SERVICE_BATCH", "all")).strip().lower()

if SERVICE_BATCH == "2":
    AUTO_FRIEND_SERVERS = dict(BATCH_2_SERVERS)
    print(f"[*] auto_friend_config: Loaded BATCH 2 ({len(AUTO_FRIEND_SERVERS)} servers configured)")
elif SERVICE_BATCH in ("all", "0"):
    AUTO_FRIEND_SERVERS = {**BATCH_1_SERVERS, **BATCH_2_SERVERS}
    print(f"[*] auto_friend_config: Loaded ALL BATCHES ({len(AUTO_FRIEND_SERVERS)} servers configured)")
else:
    AUTO_FRIEND_SERVERS = dict(BATCH_1_SERVERS)
    print(f"[*] auto_friend_config: Loaded BATCH 1 ({len(AUTO_FRIEND_SERVERS)} servers configured)")

# Optional overrides from local servers_config.json (only if no explicit SERVICE_BATCH is set)
if os.path.exists(JSON_CONFIG_PATH) and "SERVICE_BATCH" not in os.environ:
    try:
        with open(JSON_CONFIG_PATH, "r", encoding="utf-8") as f:
            json_servers = json.load(f)
            if isinstance(json_servers, dict) and len(json_servers) > 0:
                AUTO_FRIEND_SERVERS.clear()
                AUTO_FRIEND_SERVERS.update(json_servers)
                print(f"[*] auto_friend_config: Overridden with {len(AUTO_FRIEND_SERVERS)} servers from {JSON_CONFIG_PATH}")
    except Exception as e:
        print(f"[!] Warning: Could not parse {JSON_CONFIG_PATH}: {e}")
