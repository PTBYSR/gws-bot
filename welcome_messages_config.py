"""
welcome_messages_config.py — Manages the post-acceptance welcome drip sequence configuration.
Loads and hot-reloads welcome_messages_config.json, with template variable formatting.
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "welcome_messages_config.json")

_CACHED_CONFIG: Optional[Dict[str, Any]] = None
_LAST_MTIME: float = 0.0

DEFAULT_MESSAGES = [
    {
        "step": 1,
        "type": "text",
        "typing_seconds": 3,
        "delay_after_seconds": 5,
        "message": "Hey {name}! Thanks for connecting 👋 Saw you joined {server}."
    },
    {
        "step": 2,
        "type": "text",
        "typing_seconds": 4,
        "delay_after_seconds": 6,
        "message": "How long have you been trading or investing in the markets?"
    },
    {
        "step": 3,
        "type": "photo",
        "typing_seconds": 3,
        "delay_after_seconds": 5,
        "photo_path": "assets/welcome_sample.png",
        "message": "Check this out — this was one of our top setups from today's session."
    },
    {
        "step": 4,
        "type": "text",
        "typing_seconds": 4,
        "delay_after_seconds": 0,
        "message": "Let me know if you want me to share the breakdown or if you have any questions!"
    }
]

def load_welcome_config() -> Dict[str, Any]:
    """Load configuration from JSON with hot-reload support on file change."""
    global _CACHED_CONFIG, _LAST_MTIME

    if not os.path.exists(CONFIG_PATH):
        return {
            "enabled": True,
            "messages": DEFAULT_MESSAGES
        }

    try:
        current_mtime = os.path.getmtime(CONFIG_PATH)
        if _CACHED_CONFIG is not None and current_mtime == _LAST_MTIME:
            return _CACHED_CONFIG

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        _CACHED_CONFIG = data
        _LAST_MTIME = current_mtime
        return data
    except Exception as e:
        logger.error(f"[!] Failed to read {CONFIG_PATH}: {e}")
        if _CACHED_CONFIG:
            return _CACHED_CONFIG
        return {
            "enabled": True,
            "messages": DEFAULT_MESSAGES
        }

def get_welcome_sequence(server_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get the ordered list of messages to send.
    Supports server overrides if 'server_overrides' dictionary is configured.
    """
    cfg = load_welcome_config()
    if not cfg.get("enabled", True):
        return []

    # Check for server-specific override
    if server_id:
        overrides = cfg.get("server_overrides", {})
        if str(server_id) in overrides:
            return overrides[str(server_id)]

    # Fall back to 'messages' or 'default_sequence'
    return cfg.get("messages") or cfg.get("default_sequence") or DEFAULT_MESSAGES

def format_template(template_str: str, user=None, server_name: str = "the server", sender_label: str = "Support") -> str:
    """Format string with dynamic variables like {name}, {username}, {server}, {sender}."""
    if not template_str:
        return ""

    user_name = "there"
    username = "user"
    if user:
        # discord.User or Member
        user_name = getattr(user, "display_name", None) or getattr(user, "name", "there")
        username = getattr(user, "name", "user")

    clean_server = server_name if server_name and server_name != "Unknown" else "our community"

    replacements = {
        "{name}": str(user_name),
        "{username}": str(username),
        "{server}": str(clean_server),
        "{sender}": str(sender_label)
    }

    result = template_str
    for k, v in replacements.items():
        result = result.replace(k, v)

    return result
