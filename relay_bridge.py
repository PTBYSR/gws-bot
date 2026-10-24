"""
relay_bridge.py — Two-Way Discord Relay Hub (Channel DM Simulator).

Bridges DMs between target prospects and your private 'GWS Control' server:
1. When a prospect accepts a friend request (or DMs a sender account), a channel
   is automatically created under that sender's category: e.g. #claire-john
2. When you type in that channel from your iPhone, the message is sent directly
   as a DM to the prospect from that specific sender account.
3. Supports full in-DM formatting:
   - Native Message Replies (swiping or long-pressing Reply in Discord).
   - Image & File attachments (uploading camera roll/photos, replying to pictures).
   - Prospect Mentions: Typing @username, @them, @user, @target auto-converts to a real <@ID> mention!
4. When the prospect replies or sends pictures in DM, they appear directly in that exact channel.
"""
import os
import re
import json
import asyncio
import discord
from datetime import datetime, timezone

# GWS Control Hub Server ID
HUB_SERVER_ID = "1561888167936659528"
LOG_TARGET_USER_ID = os.environ.get("LOG_TARGET_USER_ID", "1551356562142928968")

# In-memory debounce map for inbound buzzes: target_user_id -> last_timestamp
_RECENT_INBOUND_BUZZ = {}

# Set of automated welcome drip message IDs to ensure they NEVER trigger 5-buzz inbound alerts
_AUTOMATED_DRIP_MSG_IDS = set()

def register_automated_drip_msg_id(msg_id: int):
    """Tracks message IDs sent by automated welcome drips so they are never treated as inbound replies."""
    _AUTOMATED_DRIP_MSG_IDS.add(int(msg_id))

def is_automated_welcome_message(content: str) -> bool:
    """Checks if message content matches automated welcome drip text."""
    if not content:
        return False
    phrases = [
        "admin in this server",
        "how are you doing",
        "thanks for connecting",
        "before we continue,  for security reasons",
        "before we continue, for security reasons",
        "protect our community from unwanted actions",
        "turn of the highlighted icons",
        "turn off the highlighted icons"
    ]
    clow = content.lower()
    return any(p in clow for p in phrases)

async def trigger_buzz_burst(client, target_user_id: str = None, count: int = 5, delay: float = 0.8, auto_delete_after: int = 60):
    """
    Sends a rapid burst of notifications (.) to trigger consecutive
    vibrations/chimes on the operator's mobile device (Android & iOS compatible),
    then auto-deletes them after the specified duration (Option B) to keep the DM clean.
    """
    if not client:
        return

    uid = str(target_user_id or LOG_TARGET_USER_ID or "1551356562142928968").strip()
    if not uid:
        return

    try:
        target = client.get_user(int(uid))
        if not target:
            target = await client.fetch_user(int(uid))
        if not target:
            print(f"  [!] Buzz Burst: Could not resolve operator user {uid}")
            return

        sent_pings = []
        for i in range(count):
            await asyncio.sleep(delay)
            try:
                ping_msg = await target.send(".")
                sent_pings.append(ping_msg)
            except Exception as pe:
                print(f"  [!] Failed to send burst ping #{i+1}: {pe}")

        print(f"  [⚡] Dispatched {len(sent_pings)} buzz burst notifications to {uid}")

        # Option B: Auto-delete empty pings after specified seconds
        if auto_delete_after > 0 and sent_pings:
            async def _cleanup():
                await asyncio.sleep(auto_delete_after)
                deleted = 0
                for msg in sent_pings:
                    try:
                        await msg.delete()
                        deleted += 1
                        await asyncio.sleep(0.2)
                    except Exception:
                        pass
                print(f"  [🧹] Auto-cleaned {deleted}/{len(sent_pings)} buzz burst notifications.")

            asyncio.create_task(_cleanup())

    except Exception as e:
        print(f"  [!] Failed to execute buzz burst for {uid}: {e}")

async def notify_inbound_reply(hub_client, sender_label: str, sender_name: str, target_user_id: int, content: str, channel):
    """
    Sends a DM alert to the operator with message preview + direct link when a prospect replies,
    and triggers a 5-buzz burst notification (debounced by 15s to avoid duplicate bursts if typing fast).
    """
    if not hub_client:
        return

    uid = str(LOG_TARGET_USER_ID or "1551356562142928968").strip()
    now_ts = asyncio.get_event_loop().time()
    last_ts = _RECENT_INBOUND_BUZZ.get(target_user_id, 0)

    try:
        target = hub_client.get_user(int(uid))
        if not target:
            target = await hub_client.fetch_user(int(uid))
        if target:
            chan_link = f"https://discord.com/channels/{HUB_SERVER_ID}/{channel.id}"
            preview = (content[:250] + "...") if len(content) > 250 else (content or "[Sent a photo / attachment]")
            alert_msg = (
                f"💬 **New Reply from `{sender_name}`** (`{sender_label}` thread)!\n"
                f"> {preview}\n"
                f"🔗 **Chat Here**: <#{channel.id}> ([Open Channel]({chan_link}))"
            )
            await target.send(alert_msg)

            # Trigger 5-buzz burst if not buzzed for this prospect in the last 15 seconds
            if now_ts - last_ts > 15:
                _RECENT_INBOUND_BUZZ[target_user_id] = now_ts
                asyncio.create_task(
                    trigger_buzz_burst(
                        client=hub_client,
                        target_user_id=uid,
                        count=5,
                        delay=0.8,
                        auto_delete_after=60
                    )
                )
    except Exception as e:
        print(f"  [!] Failed to send inbound DM alert: {e}")

# In-memory channel mappings:
# CHANNEL_ID -> {"target_user_id": str, "target_name": str, "sender_label": str, "sender_token": str}
CHANNEL_TO_TARGET = {}
# f"{sender_label}:{target_user_id}" -> channel_id
TARGET_TO_CHANNEL = {}

# Message ID mapping for 2-way native Discord replies:
# HUB_MSG_ID -> {"dm_msg_id": int, "dm_channel_id": int}
HUB_TO_DM_MSG = {}
# DM_MSG_ID -> hub_msg_id (int)
DM_TO_HUB_MSG = {}

# Mongo DB reference (set from main.py)
_DB_REF = None

def set_db_ref(db):
    global _DB_REF
    _DB_REF = db

async def load_relay_mappings_from_db():
    """Load existing relay channels and recent message mappings into memory on bot startup."""
    global CHANNEL_TO_TARGET, TARGET_TO_CHANNEL, HUB_TO_DM_MSG, DM_TO_HUB_MSG
    if _DB_REF is None:
        return
    try:
        cursor = _DB_REF.relay_mappings.find({})
        async for doc in cursor:
            cid = str(doc.get("channel_id"))
            key = f"{doc.get('sender_label')}:{doc.get('target_user_id')}"
            CHANNEL_TO_TARGET[cid] = {
                "target_user_id": str(doc.get("target_user_id")),
                "target_name": doc.get("target_name", "user"),
                "sender_label": doc.get("sender_label"),
                "sender_token": doc.get("sender_token")
            }
            TARGET_TO_CHANNEL[key] = cid
        print(f"  [✓] Loaded {len(CHANNEL_TO_TARGET)} active relay channel mappings from database.")
    except Exception as e:
        print(f"  [!] Failed to load relay mappings from DB: {e}")

    try:
        # Load the 500 most recent message reply relationships
        msg_cursor = _DB_REF.relay_message_map.find({}).sort("created_at", -1).limit(500)
        loaded_msgs = 0
        async for doc in msg_cursor:
            h_id = str(doc.get("hub_msg_id"))
            d_id = int(doc.get("dm_msg_id"))
            c_id = int(doc.get("dm_channel_id"))
            HUB_TO_DM_MSG[h_id] = {"dm_msg_id": d_id, "dm_channel_id": c_id}
            DM_TO_HUB_MSG[str(d_id)] = int(h_id)
            loaded_msgs += 1
        if loaded_msgs > 0:
            print(f"  [✓] Loaded {loaded_msgs} DM message reply links from database.")
    except Exception as e:
        print(f"  [!] Failed to load relay message reply links from DB: {e}")

async def save_relay_mapping(channel_id: str, target_user_id: str, target_name: str, sender_label: str, sender_token: str):
    """Persist a new relay mapping."""
    key = f"{sender_label}:{target_user_id}"
    CHANNEL_TO_TARGET[channel_id] = {
        "target_user_id": target_user_id,
        "target_name": target_name,
        "sender_label": sender_label,
        "sender_token": sender_token
    }
    TARGET_TO_CHANNEL[key] = channel_id

    if _DB_REF is not None:
        try:
            await _DB_REF.relay_mappings.update_one(
                {"channel_id": channel_id},
                {"$set": {
                    "channel_id": channel_id,
                    "target_user_id": target_user_id,
                    "target_name": target_name,
                    "sender_label": sender_label,
                    "sender_token": sender_token,
                    "updated_at": datetime.now(timezone.utc)
                }},
                upsert=True
            )
        except Exception as e:
            print(f"  [!] Failed to save relay mapping to DB: {e}")

async def save_msg_mapping(hub_msg_id: str, dm_msg_id: int, dm_channel_id: int):
    """Store link between GWS Control channel message and DM message for native replies."""
    HUB_TO_DM_MSG[str(hub_msg_id)] = {"dm_msg_id": dm_msg_id, "dm_channel_id": dm_channel_id}
    DM_TO_HUB_MSG[str(dm_msg_id)] = int(hub_msg_id)

    if _DB_REF is not None:
        try:
            await _DB_REF.relay_message_map.update_one(
                {"hub_msg_id": str(hub_msg_id)},
                {"$set": {
                    "hub_msg_id": str(hub_msg_id),
                    "dm_msg_id": dm_msg_id,
                    "dm_channel_id": dm_channel_id,
                    "created_at": datetime.now(timezone.utc)
                }},
                upsert=True
            )
        except Exception:
            pass

def sanitize_channel_name(sender_label: str, target_name: str) -> str:
    """Format safe Discord channel name e.g. 'claire-johndoe'."""
    s_clean = re.sub(r'[^a-zA-Z0-9]', '', sender_label)[:6].lower()
    t_clean = re.sub(r'[^a-zA-Z0-9]', '', target_name)[:18].lower()
    return f"{s_clean}-{t_clean or 'user'}"

def process_outbound_mentions(content: str, target_user_id: str, target_name: str) -> str:
    """
    Substitutes tags like @dalot, @dalot___, @them, @user, @target, @prospect
    with the real Discord user mention <@USER_ID>.
    """
    if not content:
        return content

    base_name = re.sub(r'[^a-zA-Z0-9_]', '', target_name).lower()
    short_name = base_name.rstrip('_')
    name_patterns = [re.escape(base_name)]
    if short_name and short_name != base_name:
        name_patterns.append(re.escape(short_name))

    pattern_names = "|".join(name_patterns + ["target", "them", "user", "prospect", "you"])
    regex = re.compile(rf"@({pattern_names})\b", re.IGNORECASE)
    return regex.sub(f"<@{target_user_id}>", content)

async def get_or_create_relay_channel(hub_client, sender_label: str, sender_token: str, target_user, origin_server_name: str = "Unknown"):
    """
    Finds existing relay channel for this target, or creates a new one under
    the sender's category in the GWS Control Hub server.
    """
    if not hub_client:
        return None

    hub_guild = hub_client.get_guild(int(HUB_SERVER_ID))
    if not hub_guild:
        try:
            hub_guild = await hub_client.fetch_guild(int(HUB_SERVER_ID))
        except Exception as e:
            print(f"  [!] Cannot access Hub Guild {HUB_SERVER_ID}: {e}")
            return None

    target_id_str = str(target_user.id)
    target_name = target_user.name if hasattr(target_user, 'name') else "prospect"
    key = f"{sender_label}:{target_id_str}"

    # Auto-resolve origin server name if Unknown
    if origin_server_name == "Unknown":
        try:
            from auto_friend_config import AUTO_FRIEND_SERVERS
            for gid, cfg in AUTO_FRIEND_SERVERS.items():
                if cfg.get("sender_label") == sender_label or cfg.get("sender_token") == sender_token:
                    origin_server_name = cfg.get("server_name", "Unknown")
                    break
        except Exception:
            pass


    # 1. Check existing channel mapping
    if key in TARGET_TO_CHANNEL:
        cid = int(TARGET_TO_CHANNEL[key])
        existing_chan = hub_guild.get_channel(cid)
        if existing_chan:
            return existing_chan

    # 2. Check if bot has Manage Channels permission
    bot_member = hub_guild.get_member(hub_client.user.id) or await hub_guild.fetch_member(hub_client.user.id)
    if not bot_member or not (bot_member.guild_permissions.manage_channels or bot_member.guild_permissions.administrator):
        print(f"  [!] Cannot create relay channel: king_arthur0001 is missing 'Manage Channels' permission in GWS Control.")
        return None

    # 3. Find or create Category for this sender
    category_name = f"📁 {sender_label}"
    category = discord.utils.get(hub_guild.categories, name=category_name)
    if not category:
        try:
            category = await hub_guild.create_category(name=category_name)
        except Exception as e:
            print(f"  [!] Failed to create category {category_name}: {e}")
            category = None

    # 4. Create Channel for this prospect
    chan_name = sanitize_channel_name(sender_label, target_name)
    topic_str = f"Target ID: {target_id_str} | Sender: {sender_label} | Origin: {origin_server_name}"

    try:
        new_channel = await hub_guild.create_text_channel(
            name=chan_name,
            category=category,
            topic=topic_str
        )
        
        # Save mapping
        await save_relay_mapping(
            channel_id=str(new_channel.id),
            target_user_id=target_id_str,
            target_name=target_name,
            sender_label=sender_label,
            sender_token=sender_token
        )

        # Send introductory banner
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        mention_prefix = f"<@{LOG_TARGET_USER_ID}> " if LOG_TARGET_USER_ID else ""
        banner = (
            f"🎉 {mention_prefix}**Live Relay Bridge Active!**\n"
            f"• **Prospect**: `{target_name}` (`{target_id_str}`)\n"
            f"• **Sender Account**: `{sender_label}`\n"
            f"• **Origin Server**: `{origin_server_name}`\n"
            f"• **Started**: `{timestamp} UTC`\n"
            f"─────────────────────────────────────\n"
            f"💬 **How to chat from your iPhone:**\n"
            f"• Type your message directly here — `{sender_label}` sends it as a DM to `{target_name}`!\n"
            f"• **Replies**: Swipe or tap 'Reply' on any message (text or photo) to reply natively.\n"
            f"• **Photos**: Upload pictures from your camera roll — they are sent as native image files.\n"
            f"• **Mentions**: Type `@them`, `@user`, or `@{target_name}` to ping them in DM.\n"
            f"• **Auto-Drip**: Type `!drip` or `!welcome` to trigger the automated 4-message welcome sequence.\n"
            f"*(A ✅ reaction confirms successful delivery).* "
        )
        await new_channel.send(banner)
        print(f"  [+] Created Relay Channel: #{new_channel.name} ({new_channel.id}) in GWS Control Hub!")
        return new_channel
    except Exception as e:
        print(f"  [!] Failed to create relay channel for {target_name}: {e}")
        return None

async def handle_outbound_relay_message(message, sender_clients_map):
    """
    Called when you send a message in GWS Control.
    Delivers the message as a DM from the mapped sender account to the prospect.
    Supports replies, images/attachments, and mention replacement.
    """
    if not message.guild or str(message.guild.id) != str(HUB_SERVER_ID):
        return False
    
    # Ignore bot's own messages
    if message.author.bot:
        return False

    cid = str(message.channel.id)
    mapping = CHANNEL_TO_TARGET.get(cid)
    if not mapping:
        return False

    sender_token = mapping["sender_token"]
    target_user_id = mapping["target_user_id"]
    target_name = mapping.get("target_name", "user")
    sender_label = mapping["sender_label"]

    client = sender_clients_map.get(sender_token)
    if not client or not client.is_ready():
        await message.channel.send(f"⚠️ Sender account `{sender_label}` is currently connecting or offline. Try again in a moment.")
        return True

    try:
        target_user = client.get_user(int(target_user_id))
        if not target_user:
            target_user = await client.fetch_user(int(target_user_id))

        if not target_user:
            await message.channel.send(f"❌ Could not find prospect user `{target_user_id}` on Discord.")
            return True

        # Check for manual drip test command
        if message.content and message.content.strip().lower() in ("!drip", "!welcome"):
            from auto_friend import run_welcome_drip_sequence
            await message.add_reaction("⏳")
            asyncio.create_task(
                run_welcome_drip_sequence(
                    sender_token=sender_token,
                    sender_label=sender_label,
                    friend_user=target_user,
                    origin_name="Manual Trigger",
                    relay_channel=message.channel,
                    force=True
                )
            )
            return True

        # 1. Process Mentions (@them, @user, @prospect, @username -> <@id>)
        content = process_outbound_mentions(message.content or "", target_user_id, target_name)

        # 2. Process Attachments / Pictures
        files = []
        if message.attachments:
            for a in message.attachments:
                try:
                    f = await a.to_file()
                    files.append(f)
                except Exception as err:
                    print(f"  [!] Failed to stream outbound attachment {a.filename}: {err}")
                    # Fallback to appending URL if file conversion fails
                    content = f"{content}\n{a.url}" if content else a.url

        if not content.strip() and not files:
            return True

        # 3. Check if replying to a specific message or picture
        dm_channel = target_user.dm_channel or await target_user.create_dm()
        dm_reference = None
        if message.reference and message.reference.message_id:
            ref_hub_id = str(message.reference.message_id)
            dm_meta = HUB_TO_DM_MSG.get(ref_hub_id)
            if dm_meta:
                dm_reference = discord.MessageReference(
                    message_id=int(dm_meta["dm_msg_id"]),
                    channel_id=int(dm_meta["dm_channel_id"]),
                    fail_if_not_exists=False
                )

        # 4. Send DM as the sender account!
        dm_sent = None
        if dm_reference:
            try:
                dm_sent = await dm_channel.send(
                    content=content if content.strip() else None,
                    files=files if files else None,
                    reference=dm_reference
                )
            except Exception as re:
                print(f"  [!] Reference send error ({re}), sending as standard DM...")
                dm_sent = None

        if not dm_sent:
            dm_sent = await dm_channel.send(
                content=content if content.strip() else None,
                files=files if files else None
            )

        # 5. Link this outbound message for future replies
        if dm_sent:
            await save_msg_mapping(str(message.id), dm_sent.id, dm_channel.id)

        # React with checkmark to confirm delivery to user on iPhone!
        await message.add_reaction("✅")
        print(f"  [→] Outbound Relay: Delivered message to {target_user.name} via {sender_label}")
        return True

    except discord.Forbidden:
        await message.channel.send(f"❌ Cannot DM user: They may have DMs closed or unfriended `{sender_label}`.")
        await message.add_reaction("❌")
        return True
    except Exception as e:
        await message.channel.send(f"⚠️ Failed to deliver DM via `{sender_label}`: `{e}`")
        await message.add_reaction("⚠️")
        return True

async def handle_inbound_dm(sender_label: str, sender_token: str, dm_message, hub_client):
    # 0. Never process inbound DMs if the author is a bot, or if it is an automated welcome message
    if dm_message.author.bot:
        return
    if dm_message.id in _AUTOMATED_DRIP_MSG_IDS or is_automated_welcome_message(dm_message.content):
        return

    # Find or create channel
    channel = await get_or_create_relay_channel(
        hub_client=hub_client,
        sender_label=sender_label,
        sender_token=sender_token,
        target_user=dm_message.author
    )

    if channel:
        content = dm_message.content or ""
        sender_name = dm_message.author.name

        # 1. Process Attachments / Pictures
        files = []
        if dm_message.attachments:
            for a in dm_message.attachments:
                try:
                    f = await a.to_file()
                    files.append(f)
                except Exception as err:
                    print(f"  [!] Failed to stream inbound attachment {a.filename}: {err}")
                    content = f"{content}\n{a.url}" if content else a.url

        # 2. Check if the prospect replied to one of our DMs
        hub_reference = None
        if dm_message.reference and dm_message.reference.message_id:
            ref_dm_id = str(dm_message.reference.message_id)
            hub_ref_id = DM_TO_HUB_MSG.get(ref_dm_id)
            if hub_ref_id:
                hub_reference = discord.MessageReference(
                    message_id=int(hub_ref_id),
                    channel_id=channel.id,
                    fail_if_not_exists=False
                )

        header = f"👤 **{sender_name}**:"
        text = f"{header} {content}" if content else header

        sent_hub_msg = None
        if hub_reference:
            try:
                sent_hub_msg = await channel.send(
                    content=text,
                    files=files if files else None,
                    reference=hub_reference
                )
            except Exception:
                sent_hub_msg = None

        if not sent_hub_msg:
            sent_hub_msg = await channel.send(
                content=text,
                files=files if files else None
            )

        # 3. Store link for 2-way native replies
        if sent_hub_msg:
            await save_msg_mapping(str(sent_hub_msg.id), dm_message.id, dm_message.channel.id)

        print(f"  [←] Inbound Relay: Mirrored DM from {sender_name} to #{channel.name}")

        # 4. Notify Operator in DM + 5-Buzz Burst Notification (Option B: auto-clean after 60s)
        asyncio.create_task(
            notify_inbound_reply(
                hub_client=hub_client,
                sender_label=sender_label,
                sender_name=sender_name,
                target_user_id=dm_message.author.id,
                content=content,
                channel=channel
            )
        )

async def handle_outbound_relay_edit(before, after, sender_clients_map):
    """
    Called when you edit a message in GWS Control on your iPhone.
    Updates the sent message in the prospect's DM.
    """
    if not after.guild or str(after.guild.id) != str(HUB_SERVER_ID):
        return False
    if after.author.bot:
        return False

    cid = str(after.channel.id)
    mapping = CHANNEL_TO_TARGET.get(cid)
    if not mapping:
        return False

    dm_meta = HUB_TO_DM_MSG.get(str(after.id))
    if not dm_meta:
        return False

    sender_token = mapping["sender_token"]
    sender_label = mapping["sender_label"]
    target_user_id = mapping["target_user_id"]
    target_name = mapping.get("target_name", "user")

    client = sender_clients_map.get(sender_token)
    if not client or not client.is_ready():
        return False

    try:
        dm_channel = client.get_channel(int(dm_meta["dm_channel_id"]))
        if not dm_channel:
            dm_channel = await client.fetch_channel(int(dm_meta["dm_channel_id"]))

        if dm_channel:
            new_content = process_outbound_mentions(after.content or "", target_user_id, target_name)
            partial = dm_channel.get_partial_message(int(dm_meta["dm_msg_id"]))
            await partial.edit(content=new_content)
            await after.add_reaction("✏️")
            print(f"  [✏️] Outbound Relay: Edited message in DM via {sender_label}")
            return True
    except Exception as e:
        print(f"  [!] Failed to edit outbound DM message: {e}")
        return False

async def handle_outbound_relay_delete(message, sender_clients_map):
    """
    Called when you delete a message in GWS Control on your iPhone.
    Deletes the sent message in the prospect's DM.
    """
    if not message.guild or str(message.guild.id) != str(HUB_SERVER_ID):
        return False
    if message.author.bot:
        return False

    cid = str(message.channel.id)
    mapping = CHANNEL_TO_TARGET.get(cid)
    if not mapping:
        return False

    dm_meta = HUB_TO_DM_MSG.get(str(message.id))
    if not dm_meta:
        return False

    sender_token = mapping["sender_token"]
    sender_label = mapping["sender_label"]

    client = sender_clients_map.get(sender_token)
    if not client or not client.is_ready():
        return False

    try:
        dm_channel = client.get_channel(int(dm_meta["dm_channel_id"]))
        if not dm_channel:
            dm_channel = await client.fetch_channel(int(dm_meta["dm_channel_id"]))

        if dm_channel:
            partial = dm_channel.get_partial_message(int(dm_meta["dm_msg_id"]))
            await partial.delete()
            print(f"  [🗑️] Outbound Relay: Deleted message in DM via {sender_label}")
            return True
    except Exception as e:
        print(f"  [!] Failed to delete outbound DM message: {e}")
        return False

async def handle_inbound_dm_edit(sender_label: str, sender_token: str, dm_message, hub_client):
    """
    Called when the prospect edits their DM message.
    Updates the mirrored message in the GWS Control channel.
    """
    ref_dm_id = str(dm_message.id)
    hub_msg_id = DM_TO_HUB_MSG.get(ref_dm_id)
    if not hub_msg_id or not hub_client:
        return

    key = f"{sender_label}:{dm_message.author.id}"
    cid = TARGET_TO_CHANNEL.get(key)
    if not cid:
        return

    hub_channel = hub_client.get_channel(int(cid))
    if not hub_channel:
        try:
            hub_channel = await hub_client.fetch_channel(int(cid))
        except Exception:
            return

    if hub_channel:
        try:
            partial_hub = hub_channel.get_partial_message(int(hub_msg_id))
            sender_name = dm_message.author.name
            await partial_hub.edit(content=f"👤 **{sender_name}** *(edited)*: {dm_message.content}")
            print(f"  [✏️] Inbound Relay: Updated edited message from {sender_name} in #{hub_channel.name}")
        except Exception as e:
            print(f"  [!] Failed to update edited message in Hub: {e}")

async def handle_inbound_dm_delete(sender_label: str, sender_token: str, dm_message, hub_client):
    """
    Called when the prospect deletes/unsends a DM.
    Marks the message in GWS Control with strikethrough so you can still see what was unsent!
    """
    ref_dm_id = str(dm_message.id)
    hub_msg_id = DM_TO_HUB_MSG.get(ref_dm_id)
    if not hub_msg_id or not hub_client:
        return

    key = f"{sender_label}:{dm_message.author.id}"
    cid = TARGET_TO_CHANNEL.get(key)
    if not cid:
        return

    hub_channel = hub_client.get_channel(int(cid))
    if not hub_channel:
        try:
            hub_channel = await hub_client.fetch_channel(int(cid))
        except Exception:
            return

    if hub_channel:
        try:
            hub_msg = await hub_channel.fetch_message(int(hub_msg_id))
            if hub_msg:
                orig_text = hub_msg.content
                # Strip prefix
                prefix = f"👤 **{dm_message.author.name}**:"
                if orig_text.startswith(prefix):
                    raw = orig_text[len(prefix):].strip()
                    await hub_msg.edit(content=f"👤 **{dm_message.author.name}**: ~~{raw}~~ 🗑️ *(unsent)*")
                else:
                    await hub_msg.edit(content=f"{orig_text} 🗑️ *(unsent by prospect)*")
                await hub_msg.add_reaction("🗑️")
                print(f"  [🗑️] Inbound Relay: Marked unsent message from {dm_message.author.name} in #{hub_channel.name}")
        except Exception as e:
            print(f"  [!] Failed to update deleted message in Hub: {e}")

