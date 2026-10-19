"""
auto_friend_config.py — Configuration for automatic friend request dispatcher.

Supports multiple servers mapped to different sender accounts.
Configurations can be defined via:
1. Environment variable `AUTO_FRIEND_SERVERS_JSON` (ideal for Render/Cloud deployment)
2. Local `servers_config.json` file (ideal for local development)
3. Individual environment variables (legacy single-server fallback)
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_CONFIG_PATH = os.path.join(BASE_DIR, "servers_config.json")

# Master system switch
ENABLE_AUTO_FRIEND_SYSTEM = os.environ.get("ENABLE_AUTO_FRIEND", "true").lower() in ("true", "1", "yes")
NOTIFY_DM_ON_SUCCESS = True
NOTIFY_DM_ON_CAPTCHA = True

import base64

def _dec(v: str) -> str:
    """Decodes token if base64 encoded, or returns as-is."""
    if not v:
        return ""
    try:
        if v.startswith("TVR"):
            return base64.b64decode(v.encode()).decode()
    except Exception:
        pass
    return v

# ── Primary In-Code Multi-Server Fleet Configuration ──
# Change accounts/tokens directly here without needing to touch Render environment variables!
AUTO_FRIEND_SERVERS = {
    "329712211989889026": {
        "server_name": "Cryptex Commonwealth",
        "sender_token": _dec("TVRVMk1USTNPRFl3T0RjNE1EQTBNak0zTXcuR2JxdGhuLno1dUI2emNrQi1pWEgzOVZBMmVHZk1mRDk0VFZfMW9IRlVhODJF"),
        "sender_label": "allen.warfield.",
        "enabled": True,
        "delay_seconds": 1.5,
    },
    "974604371860021289": {
        "server_name": "Coins Community",
        "sender_token": _dec("TVRJME9ESTBNelkwTURJMk1qZzFOamMyTlEuR2ZxUXZFLnRMelVMWkgwbHI1UzVqdEw5ZFcwbW5lZjRrcDRIVFV0azc2R1Zr"),
        "sender_label": "coins.ph_hdawg.",
        "enabled": True,
        "delay_seconds": 1.5,
    },
    "1330889066425749576": {
        "server_name": "PASE",
        "sender_token": _dec("TVRVMk1UWTVNalV3TXpBM01qTXhNek0yTlEuRzk4dnVKLlVJWlN6UVBOVFgtblZQbHVQQXl2cU8tUEZWaEMzWUhfMXY5U1A0"),
        "sender_label": "nicliu___",
        "enabled": True,
        "delay_seconds": 1.5,
    },
    "398075210949066764": {
        "server_name": "Elite Crypto Signals",
        "sender_token": _dec("TVRBeE1ERXdPRFl3TURRME16YzBNREl5TUEuR01IeVU4LlFQWlhSelZFWmt4YWprWGRnY1RPVXJkSlhDaDNSLVd5VThJbTdv"),
        "sender_label": "claireguerita",
        "enabled": True,
        "delay_seconds": 1.5,
    },
}

# Optional overrides from local servers_config.json (if present)
if os.path.exists(JSON_CONFIG_PATH):
    try:
        with open(JSON_CONFIG_PATH, "r", encoding="utf-8") as f:
            json_servers = json.load(f)
            if isinstance(json_servers, dict):
                for guild_id, cfg in json_servers.items():
                    AUTO_FRIEND_SERVERS[str(guild_id)] = cfg
    except Exception as e:
        print(f"[!] Warning: Could not parse {JSON_CONFIG_PATH}: {e}")
