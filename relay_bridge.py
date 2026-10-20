"""
relay_bridge.py — Two-Way Discord Relay Hub (Channel DM Simulator).

Bridges DMs between target prospects and your private 'GWS Control' server:
1. When a prospect accepts a friend request (or DMs a sender account), a channel
   is automatically created under that sender's category: e.g. #claire-john
2. When you type in that channel from your iPhone, the message is sent directly
   as a DM to the prospect from that specific sender account.
3. When the prospect replies in DM, their reply appears in that exact channel.
"""
import os
import re
import json
import asyncio
import discord
from datetime import datetime, timezone

# GWS Control Hub Server ID
HUB_SERVER_ID = "1561888167936659528"

# In-memory mappings:
# CHANNEL_ID -> {"target_user_id": str, "target_name": str, "sender_label": str, "sender_token": str}
CHANNEL_TO_TARGET = {}
# f"{sender_label}:{target_user_id}" -> channel_id
TARGET_TO_CHANNEL = {}

# Mongo DB reference (set from main.py)
_DB_REF = None

def set_db_ref(db):
    global _DB_REF
    _DB_REF = db

async def load_relay_mappings_from_db():
    """Load existing relay channels into memory on bot startup."""
    global CHANNEL_TO_TARGET, TARGET_TO_CHANNEL
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

def sanitize_channel_name(sender_label: str, target_name: str) -> str:
    """Format safe Discord channel name e.g. 'claire-johndoe'."""
    s_clean = re.sub(r'[^a-zA-Z0-9]', '', sender_label)[:6].lower()
    t_clean = re.sub(r'[^a-zA-Z0-9]', '', target_name)[:18].lower()
    return f"{s_clean}-{t_clean or 'user'}"

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
        banner = (
            f"🎉 **Live Relay Bridge Active!**\n"
            f"• **Prospect**: `{target_name}` (`{target_id_str}`)\n"
            f"• **Sender Account**: `{sender_label}`\n"
            f"• **Origin Server**: `{origin_server_name}`\n"
            f"• **Started**: `{timestamp} UTC`\n"
            f"─────────────────────────────────────\n"
            f"💬 **How to chat from your iPhone:**\n"
            f"Type your message directly in this channel. `{sender_label}` will automatically deliver it as a DM to `{target_name}`!\n"
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

        # Forward content
        content = message.content or ""
        if message.attachments:
            att_urls = "\n".join([a.url for a in message.attachments])
            content = f"{content}\n{att_urls}" if content else att_urls

        if not content.strip():
            return True

        # Send DM as the sender account!
        await target_user.send(content)
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
    """
    Called when a prospect DMs one of your sender accounts.
    Mirrors their message into their assigned channel in GWS Control.
    """
    # Find or create channel
    channel = await get_or_create_relay_channel(
        hub_client=hub_client,
        sender_label=sender_label,
        sender_token=sender_token,
        target_user=dm_message.author
    )

    if channel:
        content = dm_message.content or ""
        if dm_message.attachments:
            att_urls = "\n".join([a.url for a in dm_message.attachments])
            content = f"{content}\n{att_urls}" if content else att_urls

        sender_name = dm_message.author.name
        await channel.send(f"👤 **{sender_name}**: {content}")
        print(f"  [←] Inbound Relay: Mirrored DM from {sender_name} to #{channel.name}")
