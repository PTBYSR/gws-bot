"""
auto_friend.py — Gateway-Connected Dispatcher Module (Solution B).
Maintains an active Discord Gateway WebSocket session for sender account(s),
ensuring requests carry a live session ID, TLS browser fingerprint, and heartbeats.
Also listens for relationship updates to detect friend request acceptances.
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

# Reference to the main listener client + log target user ID (set by main.py on startup)
_LISTENER_CLIENT_REF = None
_LOG_TARGET_USER_ID = None
_NOTIFIED_ACCEPTS = set()
_RECENT_DISPATCHES = set()

def set_listener_ref(listener_client, log_target_user_id: str):
    """Called from main.py to pass the listener client so sender clients can relay DM alerts."""
    global _LISTENER_CLIENT_REF, _LOG_TARGET_USER_ID
    _LISTENER_CLIENT_REF = listener_client
    _LOG_TARGET_USER_ID = log_target_user_id

async def notify_friend_accepted(sender_label: str, friend_user, sender_token: str = ""):
    """Send a DM alert, spawn a dedicated relay channel in GWS Control Hub, and log."""
    if not friend_user:
        return

    friend_id = str(friend_user.id)
    notif_key = f"{sender_label}:{friend_id}"
    if notif_key in _NOTIFIED_ACCEPTS:
        return
    _NOTIFIED_ACCEPTS.add(notif_key)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    friend_name = friend_user.name if hasattr(friend_user, 'name') else "Unknown"

    print(f"  [🎉] Friend request ACCEPTED! {friend_name} ({friend_id}) accepted {sender_label}'s request at {timestamp} UTC")

    # 1. Spawn a dedicated Relay Channel in GWS Control Hub for chatting
    try:
        if _LISTENER_CLIENT_REF and sender_token:
            from relay_bridge import get_or_create_relay_channel
            origin_name = "Unknown"
            try:
                from auto_friend_config import AUTO_FRIEND_SERVERS
                for gid, cfg in AUTO_FRIEND_SERVERS.items():
                    if cfg.get("sender_label") == sender_label or cfg.get("sender_token") == sender_token:
                        origin_name = cfg.get("server_name", "Unknown")
                        break
            except Exception:
                pass

            await get_or_create_relay_channel(
                hub_client=_LISTENER_CLIENT_REF,
                sender_label=sender_label,
                sender_token=sender_token,
                target_user=friend_user,
                origin_server_name=origin_name
            )
    except Exception as e:
        print(f"  [!] Failed to spawn relay channel: {e}")


    # 2. Send DM alert via the listener bot
    if _LISTENER_CLIENT_REF and _LOG_TARGET_USER_ID:
        try:
            target = _LISTENER_CLIENT_REF.get_user(int(_LOG_TARGET_USER_ID))
            if not target:
                target = await _LISTENER_CLIENT_REF.fetch_user(int(_LOG_TARGET_USER_ID))
            if target:
                msg = (
                    f"🎉 **Friend Request Accepted!**\n"
                    f"• **Accepted By**: `{friend_name}` (`{friend_id}`)\n"
                    f"• **Sender Account**: `{sender_label}`\n"
                    f"• **Timestamp**: `{timestamp} UTC`\n"
                    f"💬 *A dedicated chat channel was created in GWS Control for you to DM them!*"
                )
                await target.send(msg)
        except Exception as e:
            print(f"  [!] Failed to send acceptance DM alert: {e}")

async def start_sender_gateway_client(token: str, label: str):
    """
    Connect a sender account to Discord Gateway in the background (Solution B).
    Maintains active heartbeat and session ID to simulate real browser presence.
    Also listens for relationship updates and inbound DMs for 2-way relay.
    """
    if not token or token in SENDER_CLIENTS:
        return

    client = discord.Client()
    SENDER_CLIENTS[token] = client

    @client.event
    async def on_ready():
        print(f"  [+] Auto-Friend Sender Online via Gateway: {client.user} ({label})")
        print(f"      ↳ Gateway Latency: {round(client.latency * 1000)}ms | Ready for instant requests")
        # Log initial outgoing pending count
        outgoing = [r for r in client.relationships if r.type == discord.RelationshipType.outgoing_request]
        print(f"      ↳ Outgoing Pending Requests: {len(outgoing)}")

    @client.event
    async def on_relationship_update(before, after):
        """Fires when a relationship status changes (e.g. outgoing_request -> friend)."""
        if (before.type == discord.RelationshipType.outgoing_request and
                after.type == discord.RelationshipType.friend):
            await notify_friend_accepted(sender_label=label, friend_user=after.user, sender_token=token)

    @client.event
    async def on_relationship_add(relationship):
        """Fires when a new relationship is created (could be an acceptance if type is friend)."""
        if relationship.type == discord.RelationshipType.friend:
            # This fires if Discord sends the relationship as a new add (instead of update)
            await notify_friend_accepted(sender_label=label, friend_user=relationship.user, sender_token=token)

    @client.event
    async def on_message(message):
        """Relay inbound DMs from prospects to the GWS Control Hub channel."""
        if message.guild is None and message.author.id != client.user.id:
            try:
                from relay_bridge import handle_inbound_dm
                if _LISTENER_CLIENT_REF:
                    await handle_inbound_dm(
                        sender_label=label,
                        sender_token=token,
                        dm_message=message,
                        hub_client=_LISTENER_CLIENT_REF
                    )
            except Exception as e:
                print(f"  [!] Error handling inbound relay DM on {label}: {e}")

    @client.event
    async def on_message_edit(before, after):
        """Relay edited DM from prospect to GWS Control Hub channel."""
        if after.guild is None and after.author.id != client.user.id:
            try:
                from relay_bridge import handle_inbound_dm_edit
                if _LISTENER_CLIENT_REF:
                    await handle_inbound_dm_edit(
                        sender_label=label,
                        sender_token=token,
                        dm_message=after,
                        hub_client=_LISTENER_CLIENT_REF
                    )
            except Exception as e:
                print(f"  [!] Error handling inbound DM edit on {label}: {e}")

    @client.event
    async def on_message_delete(message):
        """Relay deleted DM from prospect to GWS Control Hub channel."""
        if message.guild is None and message.author.id != client.user.id:
            try:
                from relay_bridge import handle_inbound_dm_delete
                if _LISTENER_CLIENT_REF:
                    await handle_inbound_dm_delete(
                        sender_label=label,
                        sender_token=token,
                        dm_message=message,
                        hub_client=_LISTENER_CLIENT_REF
                    )
            except Exception as e:
                print(f"  [!] Error handling inbound DM delete on {label}: {e}")


    @client.event
    async def on_member_join(member):
        """Allows sender/listener account to detect joins directly on the servers it belongs to."""
        guild_id = str(member.guild.id)
        if guild_id not in AUTO_FRIEND_SERVERS or not AUTO_FRIEND_SERVERS[guild_id].get("enabled"):
            return
        username_clean = f"{member.name}"
        if member.discriminator and member.discriminator != "0":
            username_clean += f"#{member.discriminator}"
        print(f"  [+] Gateway Listener ({label}) detected join: `{username_clean}` in `{member.guild.name}` ({member.guild.id})")
        await dispatch_auto_friend(member, username_clean, _LISTENER_CLIENT_REF, _LOG_TARGET_USER_ID)

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
            # 1. Primary method: Send via Mutual Server Profile (highest trust, zero stranger-search captcha)
            target_user = client.get_user(int(target_user_id))
            if not target_user:
                target_user = await client.fetch_user(int(target_user_id))

            if target_user:
                try:
                    await target_user.send_friend_request()
                    print(f"  [+] Auto-Friend SUCCESS: {sender_label} sent friend request to `{target_username}` ({target_user_id}) via Gateway Profile!")
                    return {"success": True, "sender_label": sender_label, "method": "gateway_user_profile"}
                except discord.HTTPException as he:
                    if he.status == 400 and not ("captcha" in str(he).lower()):
                        # Fallback to username
                        clean_name = target_username.split("#")[0] if "#" in target_username else target_username
                        await client.http.send_friend_request(clean_name, 0)
                        print(f"  [+] Auto-Friend SUCCESS: {sender_label} sent friend request to `{clean_name}` via Gateway Username!")
                        return {"success": True, "sender_label": sender_label, "method": "gateway_username"}
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
    """Entry point called by on_member_join in main.py or gateway listener."""
    guild_id = str(member.guild.id)
    if guild_id not in AUTO_FRIEND_SERVERS or not AUTO_FRIEND_SERVERS[guild_id].get("enabled"):
        return

    # Prevent double dispatch if both main listener and sender client catch the join event
    dedup_key = f"{guild_id}:{member.id}"
    if dedup_key in _RECENT_DISPATCHES:
        return
    _RECENT_DISPATCHES.add(dedup_key)

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
