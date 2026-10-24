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
_WELCOME_DRIPS_SENT = set()
_RECENT_DISPATCHES = set()
_RECENT_JOIN_DMS = set()

def set_listener_ref(listener_client, log_target_user_id: str):
    """Called from main.py to pass the listener client so sender clients can relay DM alerts."""
    global _LISTENER_CLIENT_REF, _LOG_TARGET_USER_ID
    _LISTENER_CLIENT_REF = listener_client
    _LOG_TARGET_USER_ID = log_target_user_id

async def send_join_alert_dm(member, username_clean: str, listener_client, log_target_user_id: str):
    """Send the standard New Join DM alert to the designated user from gateway listener."""
    if not listener_client or not log_target_user_id:
        return

    dedup_key = f"{member.guild.id}:{member.id}"
    if dedup_key in _RECENT_JOIN_DMS:
        return
    _RECENT_JOIN_DMS.add(dedup_key)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] `{username_clean}` joined `{member.guild.name}`"
    print(log_entry)

    # Save to local log file
    try:
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        with open(os.path.join(logs_dir, "joins.log"), "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"  [!] Failed to write to log file: {e}")

    # Save to MongoDB
    try:
        from relay_bridge import _DB_REF
        if _DB_REF is not None:
            await _DB_REF.joins.insert_one({
                "user_id": str(member.id),
                "username": username_clean,
                "guild_id": str(member.guild.id),
                "guild_name": member.guild.name,
                "joined_at": member.joined_at or datetime.now(timezone.utc),
                "logged_at": datetime.now(timezone.utc),
                "timestamp_str": timestamp,
                "source": "gateway_listener"
            })
    except Exception as e:
        print(f"  [!] Failed to save join to MongoDB: {e}")

    # Send DM to specified user
    try:
        target_user = (
            listener_client.get_user(int(log_target_user_id))
            or await listener_client.fetch_user(int(log_target_user_id))
        )
        if target_user:
            creation_date = "Unknown"
            if member.created_at:
                d = member.created_at
                suffix = 'th' if 11 <= d.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d.day % 10, 'th')
                creation_date = f"{d.day}{suffix} {d.strftime('%B %Y')}"

            dm_message = (
                f"**New Join**\n"
                f"• User: `{username_clean}`\n"
                f"• ID: `{member.id}`\n"
                f"• Created: `{creation_date}`\n"
                f"• Server: `{member.guild.name}`"
            )
            await target_user.send(dm_message)
            print(f"  [✓] DM alert successfully sent to {log_target_user_id} for `{username_clean}`")
    except Exception as e:
        print(f"  [!] Failed to send join DM to {log_target_user_id}: {e}")

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
    relay_chan = None
    origin_name = "Unknown"
    origin_gid = None
    try:
        from auto_friend_config import AUTO_FRIEND_SERVERS
        for gid, cfg in AUTO_FRIEND_SERVERS.items():
            if cfg.get("sender_label") == sender_label or cfg.get("sender_token") == sender_token:
                origin_name = cfg.get("server_name", "Unknown")
                origin_gid = str(gid)
                break
    except Exception:
        pass

    try:
        if _LISTENER_CLIENT_REF and sender_token:
            from relay_bridge import get_or_create_relay_channel
            relay_chan = await get_or_create_relay_channel(
                hub_client=_LISTENER_CLIENT_REF,
                sender_label=sender_label,
                sender_token=sender_token,
                target_user=friend_user,
                origin_server_name=origin_name
            )
    except Exception as e:
        print(f"  [!] Failed to spawn relay channel: {e}")

    # 2. Send DM alert via the listener bot + 5-Buzz Burst Notification
    target_uid = _LOG_TARGET_USER_ID or os.environ.get("LOG_TARGET_USER_ID", "1551356562142928968")
    if _LISTENER_CLIENT_REF and target_uid:
        try:
            target = _LISTENER_CLIENT_REF.get_user(int(target_uid))
            if not target:
                target = await _LISTENER_CLIENT_REF.fetch_user(int(target_uid))
            if target:
                from relay_bridge import HUB_SERVER_ID, trigger_buzz_burst
                link_text = ""
                if relay_chan:
                    chan_url = f"https://discord.com/channels/{HUB_SERVER_ID}/{relay_chan.id}"
                    link_text = f"\n🔗 **Direct Chat**: <#{relay_chan.id}> ([Open Channel]({chan_url}))"

                msg = (
                    f"🎉 **Friend Request Accepted!**\n"
                    f"• **Accepted By**: `{friend_name}` (`{friend_id}`)\n"
                    f"• **Sender Account**: `{sender_label}`\n"
                    f"• **Origin Server**: `{origin_name}`\n"
                    f"• **Timestamp**: `{timestamp} UTC`{link_text}\n"
                    f"💬 *A dedicated chat channel was created in GWS Control for you to DM them!*"
                )
                await target.send(msg)

                # Option B: Fire 5-buzz burst notifications (auto-cleaned after 60s)
                asyncio.create_task(
                    trigger_buzz_burst(
                        client=_LISTENER_CLIENT_REF,
                        target_user_id=target_uid,
                        count=5,
                        delay=0.8,
                        auto_delete_after=60
                    )
                )
        except Exception as e:
            print(f"  [!] Failed to send acceptance DM alert: {e}")

    # 3. Trigger automated 4-step welcome drip sequence
    try:
        asyncio.create_task(
            run_welcome_drip_sequence(
                sender_token=sender_token,
                sender_label=sender_label,
                friend_user=friend_user,
                origin_name=origin_name,
                origin_gid=origin_gid,
                relay_channel=relay_chan
            )
        )
    except Exception as e:
        print(f"  [!] Failed to schedule welcome drip sequence: {e}")

async def run_welcome_drip_sequence(
    sender_token: str,
    sender_label: str,
    friend_user,
    origin_name: str = "Unknown",
    origin_gid: str = None,
    relay_channel = None,
    force: bool = False
):
    """
    Executes the configured welcome drip sequence (4 messages with custom delays & photo support).
    Sends messages via the sender account, displays typing indicator, and mirrors each message
    into the GWS Control Hub relay channel so the operator sees the full conversation.
    """
    if not friend_user or not sender_token:
        return

    friend_id = str(friend_user.id)
    drip_key = f"{sender_label}:{friend_id}"
    if not force and drip_key in _WELCOME_DRIPS_SENT:
        return
    _WELCOME_DRIPS_SENT.add(drip_key)

    # Check MongoDB to ensure we never re-send across bot restarts
    if not force:
        try:
            from relay_bridge import _DB_REF
            if _DB_REF is not None:
                existing = await _DB_REF.welcome_drips.find_one({"sender_label": sender_label, "friend_id": friend_id})
                if existing:
                    print(f"  [ℹ] Welcome drip already sent to {friend_id} previously. Skipping.")
                    return
        except Exception as e:
            print(f"  [!] Welcome drip DB check error: {e}")

    # Load messages sequence from config
    try:
        from welcome_messages_config import get_welcome_sequence, format_template
        sequence = get_welcome_sequence(server_id=origin_gid)
    except Exception as e:
        print(f"  [!] Failed to load welcome sequence config: {e}")
        return

    if not sequence:
        return

    friend_name = getattr(friend_user, "name", "friend")
    print(f"  [🚀] Starting {len(sequence)}-step welcome sequence to {friend_name} ({friend_id}) via {sender_label}...")

    # Wait for sender client to be ready
    client = SENDER_CLIENTS.get(sender_token)
    if not client or not client.is_ready():
        for _ in range(10):
            await asyncio.sleep(1)
            client = SENDER_CLIENTS.get(sender_token)
            if client and client.is_ready():
                break

    if not client:
        print(f"  [!] Cannot run welcome drip: sender client `{sender_label}` not available.")
        return

    try:
        target_user = client.get_user(int(friend_id))
        if not target_user:
            target_user = await client.fetch_user(int(friend_id))
        if not target_user:
            print(f"  [!] Target user {friend_id} not reachable by sender {sender_label}.")
            return
        dm_channel = target_user.dm_channel or await target_user.create_dm()
    except Exception as e:
        print(f"  [!] Failed to get/create DM channel with {friend_id}: {e}")
        return

    # Post initial status in relay channel
    if relay_channel:
        try:
            await relay_channel.send(
                f"🤖 **Automated Welcome Drip Started** ({len(sequence)} messages scheduled via `{sender_label}`)"
            )
        except Exception:
            pass

    for idx, item in enumerate(sequence, start=1):
        step_num = item.get("step", idx)
        msg_type = str(item.get("type", "text")).lower()
        raw_msg = item.get("message", "")
        formatted_text = format_template(
            template_str=raw_msg,
            user=target_user,
            server_name=origin_name,
            sender_label=sender_label
        )
        typing_sec = float(item.get("typing_seconds", 3))
        delay_after_sec = float(item.get("delay_after_seconds", 5))

        # 1. Simulate typing indicator
        if typing_sec > 0:
            try:
                async with dm_channel.typing():
                    await asyncio.sleep(typing_sec)
            except Exception as te:
                print(f"  [!] Typing indicator error: {te}")
                await asyncio.sleep(typing_sec)

        # 2. Prepare and send message / photo
        sent_msg = None
        file_bytes = None
        filename = "welcome.png"
        try:
            if msg_type == "photo":
                photo_path = item.get("photo_path", "")

                if photo_path:
                    # Check if web URL
                    if photo_path.startswith("http://") or photo_path.startswith("https://"):
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(photo_path, timeout=15) as resp:
                                    if resp.status == 200:
                                        file_bytes = await resp.read()
                                        clean_url = photo_path.split("?")[0]
                                        filename = os.path.basename(clean_url) or "photo.png"
                        except Exception as dl_err:
                            print(f"  [!] Failed to download photo from {photo_path}: {dl_err}")
                    else:
                        # Local file path
                        resolved_path = photo_path
                        if not os.path.isabs(resolved_path):
                            resolved_path = os.path.join(os.path.dirname(__file__), photo_path)
                        if os.path.exists(resolved_path):
                            with open(resolved_path, "rb") as f:
                                file_bytes = f.read()
                            filename = os.path.basename(resolved_path)
                        else:
                            print(f"  [!] Photo file not found at: {resolved_path}")

                if file_bytes:
                    import io
                    discord_file = discord.File(io.BytesIO(file_bytes), filename=filename)
                    sent_msg = await dm_channel.send(
                        content=formatted_text if formatted_text else None,
                        file=discord_file
                    )
                else:
                    # Fallback to sending text caption if photo unavailable
                    if formatted_text:
                        sent_msg = await dm_channel.send(content=formatted_text)
            else:
                # Standard text message
                if formatted_text:
                    sent_msg = await dm_channel.send(content=formatted_text)

            print(f"  [✓] Sent Welcome Step {step_num}/{len(sequence)} to {friend_name} via {sender_label}")

            # 3. Mirror to GWS Control Hub relay channel
            if relay_channel:
                try:
                    from relay_bridge import save_msg_mapping
                    mirror_content = f"🤖 **[Auto-Drip {step_num}/{len(sequence)}]** `{sender_label}`:\n{formatted_text}"
                    mirror_file = None
                    if msg_type == "photo" and file_bytes:
                        import io
                        mirror_file = discord.File(io.BytesIO(file_bytes), filename=filename)

                    mirror_msg = await relay_channel.send(
                        content=mirror_content,
                        file=mirror_file
                    )

                    if sent_msg and mirror_msg:
                        await save_msg_mapping(str(mirror_msg.id), sent_msg.id, dm_channel.id)
                except Exception as me:
                    print(f"  [!] Failed to mirror welcome message to relay channel: {me}")

        except discord.Forbidden:
            print(f"  [!] Cannot DM {friend_name}: Forbidden (DMs closed or unfriended). Stopping drip.")
            if relay_channel:
                try:
                    await relay_channel.send("⚠️ **Auto-Drip Stopped**: Prospect has closed DMs or unfriended.")
                except Exception:
                    pass
            break
        except Exception as se:
            print(f"  [!] Error sending welcome step {step_num}: {se}")

        # 4. Wait configured delay before next step
        if delay_after_sec > 0 and idx < len(sequence):
            await asyncio.sleep(delay_after_sec)

    # Mark as completed in MongoDB
    try:
        from relay_bridge import _DB_REF
        if _DB_REF is not None:
            await _DB_REF.welcome_drips.insert_one({
                "sender_label": sender_label,
                "friend_id": friend_id,
                "friend_name": friend_name,
                "completed_at": datetime.now(timezone.utc),
                "steps_sent": len(sequence)
            })
    except Exception as de:
        print(f"  [!] Failed to log welcome drip completion to DB: {de}")

    print(f"  [🎉] Completed welcome drip sequence for {friend_name} ({friend_id}) via {sender_label}!")
    if relay_channel:
        try:
            await relay_channel.send("✅ **Auto-Welcome sequence completed!** You can now take over chatting manually.")
        except Exception:
            pass

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
        # 1. Send the New Join DM alert FIRST
        await send_join_alert_dm(member, username_clean, _LISTENER_CLIENT_REF, _LOG_TARGET_USER_ID)
        # 2. Dispatch Auto-Friend request
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
