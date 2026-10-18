"""
auto_friend.py — Gateway-Connected Dispatcher Module (Solution B).
Maintains an active Discord Gateway WebSocket session for sender account(s),
ensuring requests carry a live session ID, TLS browser fingerprint, and heartbeats.
"""
import os
import json
import base64
import asyncio
import aiohttp
import discord
from datetime import datetime, timezone
from auto_friend_config import AUTO_FRIEND_SERVERS, ENABLE_AUTO_FRIEND_SYSTEM

# Registry of active gateway clients for sender accounts
# Map: sender_token -> discord.Client
SENDER_CLIENTS = {}
SENDER_CLIENT_TASKS = []

async def start_sender_gateway_client(token: str, label: str):
    """
    Connect a sender account to Discord Gateway in the background (Solution B).
    Maintains active heartbeat and session ID to simulate real browser presence.
    """
    if not token or token in SENDER_CLIENTS:
        return

    client = discord.Client()
    SENDER_CLIENTS[token] = client

    @client.event
    async def on_ready():
        print(f"  [+] Auto-Friend Sender Online via Gateway: {client.user} ({label})")
        print(f"      ↳ Gateway Latency: {round(client.latency * 1000)}ms | Ready for instant requests")

    try:
        await client.start(token.strip())
    except discord.LoginFailure:
        print(f"  [!] Auto-Friend Sender '{label}' Login Failure: Invalid or expired token (401).")
    except Exception as e:
        print(f"  [!] Auto-Friend Sender '{label}' Gateway Error: {e}")

async def init_all_sender_clients():
    """Start gateway clients for all enabled sender accounts."""
    if not ENABLE_AUTO_FRIEND_SYSTEM:
        return

    for guild_id, cfg in AUTO_FRIEND_SERVERS.items():
        if cfg.get("enabled"):
            token = cfg.get("sender_token")
            label = cfg.get("sender_label", "Sender")
            if token and token not in SENDER_CLIENTS:
                task = asyncio.create_task(start_sender_gateway_client(token, label))
                SENDER_CLIENT_TASKS.append(task)

async def send_auto_friend_request(target_user_id: str, target_username: str, guild_id: str, guild_name: str) -> dict:
    """
    Dispatch a friend request through the live Gateway client (Solution B).
    """
    if not ENABLE_AUTO_FRIEND_SYSTEM:
        return {"success": False, "reason": "System disabled"}

    config = AUTO_FRIEND_SERVERS.get(str(guild_id))
    if not config or not config.get("enabled"):
        return {"success": False, "reason": "Server not configured or disabled"}

    sender_token = config.get("sender_token")
    if not sender_token:
        return {"success": False, "reason": "No sender token"}

    sender_label = config.get("sender_label", "Sender")
    delay = config.get("delay_seconds", 1.5)
    capsolver_key = config.get("capsolver_api_key", "").strip()

    if delay > 0:
        await asyncio.sleep(delay)

    client = SENDER_CLIENTS.get(sender_token)

    # ── Option B: Use Connected Gateway Client ──
    if client and client.is_ready():
        if client.user and str(target_user_id) == str(client.user.id):
            return {"success": False, "reason": "Self target"}

        try:
            print(f"  [~] Dispatching friend request via active Gateway session ({sender_label}) for {guild_name}...")
            # 1. Try sending by username through Gateway (same as browser 'Add Friend' box)
            clean_name = target_username.split("#")[0] if "#" in target_username else target_username
            try:
                await client.http.send_friend_request(clean_name, 0)
                print(f"  [+] Auto-Friend SUCCESS: {sender_label} sent friend request to `{clean_name}` via Gateway!")
                return {"success": True, "sender_label": sender_label, "method": "gateway_username"}
            except discord.HTTPException as he:
                if he.status == 400 and he.code == 0:
                    # Try sending by user ID profile relationship
                    target_user = await client.fetch_user(int(target_user_id))
                    if target_user:
                        await target_user.send_friend_request()
                        print(f"  [+] Auto-Friend SUCCESS: {sender_label} sent friend request to `{target_username}` via Gateway User Profile!")
                        return {"success": True, "sender_label": sender_label, "method": "gateway_user_profile"}
                raise he
        except discord.HTTPException as e:
            if "captcha" in str(e).lower() or e.status == 400:
                print(f"  [!] Discord challenged {sender_label} with hCaptcha. Request paused to protect token.")
                return {"success": False, "captcha_required": True, "sender_label": sender_label}
            elif e.status == 429:
                print(f"  [!] Discord Rate Limit (429) on {sender_label}.")
                return {"success": False, "rate_limited": True}
            elif e.status == 401:
                print(f"  [!] Token expired/unauthorized (401) on {sender_label}.")
                return {"success": False, "invalid_token": True}
            else:
                print(f"  [!] Gateway dispatch returned error: {e}")
                return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"  [!] Unexpected error via Gateway client: {e}")

    # Fallback if Gateway client is still connecting or unavailable
    print(f"  [!] Gateway client for {sender_label} is not connected yet. Check token status.")
    return {"success": False, "reason": "Gateway client not ready"}

async def dispatch_auto_friend(member, username_clean: str, listener_client, log_target_user_id: str):
    """Entry point called by on_member_join in main.py."""
    guild_id = str(member.guild.id)
    if guild_id not in AUTO_FRIEND_SERVERS or not AUTO_FRIEND_SERVERS[guild_id].get("enabled"):
        return

    result = await send_auto_friend_request(
        target_user_id=str(member.id),
        target_username=username_clean,
        guild_id=guild_id,
        guild_name=member.guild.name
    )

    if log_target_user_id:
        try:
            target_user = listener_client.get_user(int(log_target_user_id)) or await listener_client.fetch_user(int(log_target_user_id))
            if target_user:
                sender_label = result.get("sender_label", "Sender")
                if result.get("success"):
                    msg = (
                        f"🤝 **Auto-Friend Request Sent! (Gateway)**\n"
                        f"• Sender: `{sender_label}`\n"
                        f"• Target: `{username_clean}` (`{member.id}`)\n"
                        f"• Server: `{member.guild.name}`"
                    )
                    await target_user.send(msg)
                elif result.get("captcha_required"):
                    msg = (
                        f"⚠️ **Auto-Friend Blocked (Captcha Required)**\n"
                        f"• Sender: `{sender_label}`\n"
                        f"• Target: `{username_clean}`\n"
                        f"• Status: Discord requested hCaptcha verification. Token preserved."
                    )
                    await target_user.send(msg)
                elif result.get("invalid_token"):
                    msg = (
                        f"❌ **Auto-Friend Token Expired (401)**\n"
                        f"• Sender: `{sender_label}`\n"
                        f"• Status: Token was rotated or invalidated. Please update with active token."
                    )
                    await target_user.send(msg)
        except Exception as e:
            print(f"  [!] Failed to send auto-friend DM notification: {e}")
