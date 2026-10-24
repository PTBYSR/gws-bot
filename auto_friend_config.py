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
        "sender_token": _dec("TVRVMk1USTNPRFl3T0RjNE1EQTBNak0zTXcuR1NXdmhJLlQycVJUR2dSRU14blQ4N0NvbTZEaFZGeUp4THBWQlpNeWlDXzBR"),
        "sender_label": "allen.warfield.",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "974604371860021289": {
        "server_name": "Coins Community",
        "sender_token": _dec("TVRJME9ESTBNelkwTURJMk1qZzFOamMyTlEuR2ZxUXZFLnRMelVMWkgwbHI1UzVqdEw5ZFcwbW5lZjRrcDRIVFV0azc2R1Zr"),
        "sender_label": "coins.ph_hdawg.",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "1330889066425749576": {
        "server_name": "PASE",
        "sender_token": _dec("TVRVMk1UWTVNalV3TXpBM01qTXhNek0yTlEuR0RCU3NtLjFQSEt6S2RsMk1ldWhzaUx1SVFwMGFnVVMtQkpnVlo2QkFyeWV3"),
        "sender_label": "nicliu___",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "398075210949066764": {
        "server_name": "Elite Crypto Signals",
        "sender_token": _dec("TVRVMk16SXdOVEkyT1RJek1EUTFOamt4TXcuR0t3bDhhLjZ1ZGQ5Z2dBVFpkeFpuU3pBWFRRLUJYX2pfaFNoZ1I4b0FNcFZB"),
        "sender_label": "ecsadmin_",
        "enabled": True,
        "delay_seconds": 8.0,
    },
    "958180490957975612": {
        "server_name": "Underground Trading Company",
        "sender_token": _dec("TVRNeU16UXlOakF3TWpFd05USTNNRFF3TXcuR2lRR1JXLm9WTU8wamhqSVF4MmFOOXhwMUFMY1JTV29vLXo1RXN2RURCVVpr"),
        "sender_label": "talon.1977._",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "774685007780380683": {
        "server_name": "Team Alpha Trading",
        "sender_token": _dec("TVRVMk1qa3dPRGt4TmpZd09EWTJNelU1TlEuRzlfcEEwLnA1dEpDYl9zMTNxZVBuVG4zY2VNSlhJRGt0VmZkM0pEbmVuWFpv"),
        "sender_label": "brendan.guastaferro._",
        "enabled": True,
        "delay_seconds": 12.0,
    },
    "964204570840539166": {
        "server_name": "Stock Market Chat",
        "sender_token": _dec("TVRVMk1qa3lPVEExTkRVeE9UTTVORFF3TncuR1lMTllBLjdOR3UwOE00dFZ0SE14OG1jQUZ1eElmSlRXQjQxZ2JuNkl1QXI0"),
        "sender_label": "rhu.wan",
        "enabled": True,
        "delay_seconds": 10.0,
    },
    "1122865043952898128": {
        "server_name": "Trading University",
        "sender_token": _dec("TVRVMk1qa3pNekF3TWpZeU1UZ3lNRGszT1EuR2ZVVHVuLkdNempCenNrckFQNVhaTndLRURucHdYY0RmeGhGdHo2VVUzRENJ"),
        "sender_label": "iam.vk7._",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "1334980338467733596": {
        "server_name": "Verified Wealth",
        "sender_token": _dec("TVRBeE1ERXdPRFl3TURRME16YzBNREl5TUEuR0lBaG9QLmRoQ1lzenFJbTlKeXBWOE5XazFIYTlBNlB4QXE0Y2RuWXJiU0hn"),
        "sender_label": "adem__82099",
        "enabled": True,
        "delay_seconds": 6.0,
    },
    "563389318773604382": {
        "server_name": "Horizon Trading",
        "sender_token": _dec("TVRVMk16RTVPRFF5TVRFek1UVTVOVGt4TncuR0Fmc2RYLllCclBxWlB6TXYyclBsdDJSQmd2ZWxuSGVKMWphVDdONTRsQ3N3"),
        "sender_label": "horizon.trading",
        "enabled": True,
        "delay_seconds": 6.0,
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
