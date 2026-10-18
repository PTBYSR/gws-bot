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

AUTO_FRIEND_SERVERS = {}

# 1. Base fallback from individual environment variables (PASE / default)
default_server_id = os.environ.get("AUTO_FRIEND_SERVER_ID", "1330889066425749576")
default_sender_token = os.environ.get("AUTO_FRIEND_SENDER_TOKEN", "")
if default_sender_token:
    AUTO_FRIEND_SERVERS[str(default_server_id)] = {
        "server_name": "PASE",
        "sender_token": default_sender_token,
        "sender_label": os.environ.get("AUTO_FRIEND_SENDER_LABEL", "georgemorcos000"),
        "enabled": True,
        "delay_seconds": float(os.environ.get("AUTO_FRIEND_DELAY", "1.5")),
        "capsolver_api_key": os.environ.get("CAPSOLVER_API_KEY", ""),
    }

# 2. Load from local servers_config.json (if present)
if os.path.exists(JSON_CONFIG_PATH):
    try:
        with open(JSON_CONFIG_PATH, "r", encoding="utf-8") as f:
            json_servers = json.load(f)
            if isinstance(json_servers, dict):
                for guild_id, cfg in json_servers.items():
                    AUTO_FRIEND_SERVERS[str(guild_id)] = cfg
    except Exception as e:
        print(f"[!] Warning: Could not parse {JSON_CONFIG_PATH}: {e}")

# 3. Load from AUTO_FRIEND_SERVERS_JSON environment variable (Render / Cloud deployment)
env_json = os.environ.get("AUTO_FRIEND_SERVERS_JSON")
if env_json:
    try:
        parsed = json.loads(env_json)
        if isinstance(parsed, dict):
            for guild_id, cfg in parsed.items():
                AUTO_FRIEND_SERVERS[str(guild_id)] = cfg
    except Exception as e:
        print(f"[!] Warning: Could not parse AUTO_FRIEND_SERVERS_JSON: {e}")
