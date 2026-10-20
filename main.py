import discord
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from auto_friend import dispatch_auto_friend, init_all_sender_clients, set_listener_ref
from auto_friend_config import AUTO_FRIEND_SERVERS, ENABLE_AUTO_FRIEND_SYSTEM

# Load local .env file if present
load_dotenv()

# â”€â”€â”€ Load Environment Variables (Render/Production) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TOKEN = os.environ.get("DISCORD_TOKEN")
LOG_TARGET_USER_ID = os.environ.get("LOG_TARGET_USER_ID", "")
PORT = int(os.environ.get("PORT", 8080))
MONGO_URI = os.environ.get("MONGO_URI", "")
ALERT_WHATSAPP_NUMBER = os.environ.get("ALERT_WHATSAPP_NUMBER", "")
WHATSAPP_MONITOR_URL = os.environ.get("WHATSAPP_MONITOR_URL", "http://localhost:3005/send")

# Target servers as a comma-separated string in env, e.g., "1234,5678"
TARGET_SERVERS_STR = os.environ.get("TARGET_SERVERS", os.environ.get("TARGET_SERVERS_", ""))
TARGET_SERVERS = [s.strip() for s in TARGET_SERVERS_STR.split(",") if s.strip()]

# Create logs directory locally (ephemeral on Render free tier)
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE_PATH = os.path.join(LOGS_DIR, "joins.log")

# â”€â”€â”€ MongoDB Setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
db = None  # Will be set after connection

async def connect_mongo():
    """Connect to MongoDB Atlas and return the database handle."""
    global db
    if not MONGO_URI:
        print("  [!] MONGO_URI not set â€” running without database persistence.")
        return False

    try:
        mongo_client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        # Verify connection
        await mongo_client.admin.command("ping")
        db = mongo_client["gws_bot_logger"]
        print("  [✓] Connected to MongoDB Atlas")
        try:
            import relay_bridge
            relay_bridge.set_db_ref(db)
            await relay_bridge.load_relay_mappings_from_db()
        except Exception as re:
            print(f"  [!] Relay bridge initialization note: {re}")
        return True
    except Exception as e:
        print(f"  [!] Failed to connect to MongoDB: {e}")
        return False

async def save_join_to_db(member, username_clean, timestamp_str):
    """Persist a join event to MongoDB."""
    if db is None:
        return
    try:
        await db.joins.insert_one({
            "user_id": str(member.id),
            "username": username_clean,
            "guild_id": str(member.guild.id),
            "guild_name": member.guild.name,
            "joined_at": member.joined_at or datetime.now(timezone.utc),
            "logged_at": datetime.now(timezone.utc),
            "timestamp_str": timestamp_str,
            "source": "live"  # "live" = caught in real-time, "recovery" = caught on restart
        })
    except Exception as e:
        print(f"  [!] Failed to save join to database: {e}")

async def update_heartbeat():
    """Save a heartbeat timestamp so we know when the bot was last online."""
    if db is None:
        return
    try:
        await db.heartbeat.update_one(
            {"_id": "last_online"},
            {"$set": {"timestamp": datetime.now(timezone.utc)}},
            upsert=True
        )
    except Exception as e:
        print(f"  [!] Failed to update heartbeat: {e}")

async def get_last_online():
    """Retrieve the last heartbeat timestamp from MongoDB."""
    if db is None:
        return None
    try:
        doc = await db.heartbeat.find_one({"_id": "last_online"})
        if doc and "timestamp" in doc:
            ts = doc["timestamp"]
            # Ensure timezone-aware
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts
        return None
    except Exception as e:
        print(f"  [!] Failed to get last online timestamp: {e}")
        return None

async def heartbeat_loop():
    """Periodically update the heartbeat every 60 seconds."""
    while True:
        await update_heartbeat()
        await asyncio.sleep(60)

async def save_servers_to_db(guilds, user):
    """Save all current servers to MongoDB and a local file for safekeeping."""
    # 1. Save to Local File
    try:
        backup_path = os.path.join(LOGS_DIR, "servers_backup.txt")
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(f"Server Backup for {user} - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            f.write("="*60 + "\n")
            for guild in guilds:
                f.write(f"{guild.name} ({guild.id}) â€” {guild.member_count} members\n")
    except Exception as e:
        print(f"  [!] Failed to save local server backup: {e}")

    # 2. Save to MongoDB (The real safe for Render!)
    if db is None:
        return
    try:
        from pymongo import UpdateOne
        bulk_ops = []
        for guild in guilds:
            bulk_ops.append(
                UpdateOne(
                    {"guild_id": str(guild.id)},
                    {"$set": {
                        "guild_name": guild.name,
                        "member_count": guild.member_count,
                        "last_seen": datetime.now(timezone.utc)
                    }},
                    upsert=True
                )
            )
        if bulk_ops:
            await db.servers.bulk_write(bulk_ops)
            print(f"  [âœ“] Safely backed up {len(guilds)} servers to MongoDB (selfbot_logger.servers).")
    except Exception as e:
        print(f"  [!] Failed to backup servers to MongoDB: {e}")

# â”€â”€â”€ Client Setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
client = discord.Client()

async def send_dm_alert(member, username_clean, is_recovery=False):
    """Send a DM alert about a new member join."""
    if not LOG_TARGET_USER_ID:
        return
    try:
        target_user = (
            client.get_user(int(LOG_TARGET_USER_ID))
            or await client.fetch_user(int(LOG_TARGET_USER_ID))
        )
        if target_user:
            creation_date = "Unknown"
            if member.created_at:
                d = member.created_at
                suffix = 'th' if 11 <= d.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d.day % 10, 'th')
                creation_date = f"{d.day}{suffix} {d.strftime('%B %Y')}"

            # Indicate if this was a recovered (missed) join
            header = "**âš ï¸ Missed Join (While Offline)**" if is_recovery else "**New Join**"

            dm_message = (
                f"{header}\n"
                f"â€¢ User: `{username_clean}`\n"
                f"â€¢ ID: `{member.id}`\n"
                f"â€¢ Created: `{creation_date}`\n"
                f"â€¢ Server: `{member.guild.name}`"
            )
            if is_recovery and member.joined_at:
                dm_message += f"\nâ€¢ Joined At: `{member.joined_at.strftime('%Y-%m-%d %H:%M:%S')} UTC`"

            await target_user.send(dm_message)
            tag = "recovery DM" if is_recovery else "DM alert"
            print(f"  [âœ“] {tag} successfully sent to {LOG_TARGET_USER_ID}")
    except Exception as e:
        print(f"  [!] Failed to send DM to {LOG_TARGET_USER_ID}: {e}")

async def send_raw_whatsapp_message(text):
    """Send an arbitrary raw WhatsApp message using the monitor API."""
    if not ALERT_WHATSAPP_NUMBER:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "to": ALERT_WHATSAPP_NUMBER,
                "message": text
            }
            async with session.post(WHATSAPP_MONITOR_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    print(f"  [✓] WhatsApp message sent to {ALERT_WHATSAPP_NUMBER}")
                    return True
                else:
                    response_text = await response.text()
                    print(f"  [!] Failed to send WhatsApp message. Status: {response.status}, Response: {response_text}")
                    return False
    except Exception as e:
        print(f"  [!] Error sending WhatsApp message: {e}")
        return False

async def send_whatsapp_alert(member, username_clean, is_recovery=False):
    """Send a WhatsApp alert about a new member join using the monitor API."""
    # WhatsApp feature paused
    return

    if not ALERT_WHATSAPP_NUMBER:
        return

    try:
        creation_date = "Unknown"
        if member.created_at:
            d = member.created_at
            suffix = 'th' if 11 <= d.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d.day % 10, 'th')
            creation_date = f"{d.day}{suffix} {d.strftime('%B %Y')}"

        header = "*âš ï¸ Missed Join (While Offline)*" if is_recovery else "*New Join*"

        wa_message = (
            f"{header}\n"
            f"â€¢ User: *{username_clean}*\n"
            f"â€¢ ID: `{member.id}`\n"
            f"â€¢ Created: `{creation_date}`\n"
            f"â€¢ Server: *{member.guild.name}*"
        )
        if is_recovery and member.joined_at:
            wa_message += f"\nâ€¢ Joined At: `{member.joined_at.strftime('%Y-%m-%d %H:%M:%S')} UTC`"

        async with aiohttp.ClientSession() as session:
            payload = {
                "to": ALERT_WHATSAPP_NUMBER,
                "message": wa_message
            }
            async with session.post(WHATSAPP_MONITOR_URL, json=payload) as response:
                if response.status == 200:
                    tag = "recovery WhatsApp" if is_recovery else "WhatsApp alert"
                    print(f"  [âœ“] {tag} successfully sent to {ALERT_WHATSAPP_NUMBER}")
                else:
                    response_text = await response.text()
                    print(f"  [!] Failed to send WhatsApp alert. Status: {response.status}, Response: {response_text}")
    except Exception as e:
        print(f"  [!] Error sending WhatsApp alert to {ALERT_WHATSAPP_NUMBER}: {e}")

async def recover_missed_joins():
    """On startup, scan monitored guilds for members who joined while the bot was offline."""
    if db is None:
        print("  [~] Skipping missed join recovery (no database)")
        return

    last_online = await get_last_online()
    if last_online is None:
        print("  [~] No previous heartbeat found â€” skipping missed join recovery (first run)")
        # Set initial heartbeat
        await update_heartbeat()
        return

    now = datetime.now(timezone.utc)
    offline_duration = now - last_online
    print(f"  [~] Last online: {last_online.strftime('%Y-%m-%d %H:%M:%S')} UTC ({offline_duration} ago)")

    # Only recover if we were offline for more than 2 minutes
    # (avoids duplicate alerts during normal restarts)
    if offline_duration < timedelta(minutes=2):
        print("  [~] Offline duration too short â€” skipping recovery")
        await update_heartbeat()
        return

    recovered_count = 0

    for guild in client.guilds:
        if TARGET_SERVERS and str(guild.id) not in TARGET_SERVERS:
            continue

        try:
            # Fetch all members (requires members intent for bots, works with selfbot)
            members = guild.members

            for member in members:
                # Skip if they joined before we went offline
                if member.joined_at is None:
                    continue

                joined_at = member.joined_at
                if joined_at.tzinfo is None:
                    joined_at = joined_at.replace(tzinfo=timezone.utc)

                if joined_at <= last_online:
                    continue

                # This member joined while we were offline!
                username_clean = f"{member.name}"
                if member.discriminator and member.discriminator != "0":
                    username_clean += f"#{member.discriminator}"

                # Check if we already logged this join (avoid duplicates)
                existing = await db.joins.find_one({
                    "user_id": str(member.id),
                    "guild_id": str(guild.id),
                    "joined_at": {"$gte": last_online}
                })
                if existing:
                    continue

                timestamp_str = joined_at.strftime("%Y-%m-%d %H:%M:%S")
                log_entry = f"[{timestamp_str}] `{username_clean}` joined `{guild.name}` (RECOVERED)"
                print(log_entry)

                # Save to database
                await db.joins.insert_one({
                    "user_id": str(member.id),
                    "username": username_clean,
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "joined_at": joined_at,
                    "logged_at": datetime.now(timezone.utc),
                    "timestamp_str": timestamp_str,
                    "source": "recovery"
                })

                # Save to local file too
                try:
                    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                        f.write(log_entry + "\n")
                except Exception:
                    pass

                # Send DM alert
                await send_dm_alert(member, username_clean, is_recovery=True)
                # Send WhatsApp alert (paused)
                # await send_whatsapp_alert(member, username_clean, is_recovery=True)
                recovered_count += 1

                # Small delay to avoid rate limits
                await asyncio.sleep(1)

        except Exception as e:
            print(f"  [!] Error recovering joins for {guild.name}: {e}")

    if recovered_count > 0:
        print(f"  [âœ“] Recovered {recovered_count} missed join(s)")
    else:
        print(f"  [~] No missed joins to recover")

    # Update heartbeat after recovery
    await update_heartbeat()

@client.event
async def on_ready():
    print("=" * 60)
    print(f"  GWS Bot Logger Online")
    print(f"  Account : {client.user} ({client.user.id})")
    print(f"  Servers : {len(client.guilds)}")
    status_msg = "PASSIVE LOGGING"
    if LOG_TARGET_USER_ID:
        status_msg += f" + Discord DMs (User ID: {LOG_TARGET_USER_ID})"
    # WhatsApp feature paused
    # if ALERT_WHATSAPP_NUMBER:
    #     status_msg += f" + WhatsApp Alerts (Number: {ALERT_WHATSAPP_NUMBER})"
    print(f"  Status  : {status_msg}")
    if ENABLE_AUTO_FRIEND_SYSTEM:
        active_af = [gid for gid, cfg in AUTO_FRIEND_SERVERS.items() if cfg.get("enabled")]
        print(f"  Auto-Friend Dispatcher: ACTIVE ({len(active_af)} server(s) configured)")
        for gid in active_af:
            cfg = AUTO_FRIEND_SERVERS[gid]
            print(f"   ↳ Server {gid} ➜ Sender: {cfg.get('sender_label')}")
    else:
        print("  Auto-Friend Dispatcher: DISABLED")
    print("=" * 60)
    for guild in client.guilds:
        print(f"  [Monitoring] {guild.name} ({guild.id}) â€” {guild.member_count} members")
    print("=" * 60)

    # Backup servers to MongoDB and local file
    await save_servers_to_db(client.guilds, client.user)

    # Recover any missed joins while offline
    await recover_missed_joins()

    # Pass listener client reference for friend request acceptance alerts
    if LOG_TARGET_USER_ID:
        set_listener_ref(client, LOG_TARGET_USER_ID)

    # Start heartbeat loop in the background
    asyncio.create_task(heartbeat_loop())

    print("  Listening for new members...\n")

@client.event
async def on_guild_join(guild):
    """Fires when the selfbot account joins a new server."""
    print(f"\n[+] Joined new server: {guild.name} ({guild.id}) — {guild.member_count} members")
    await save_servers_to_db(client.guilds, client.user)

@client.event
async def on_member_join(member):
    """Fires when a new user joins any server this account is in."""
    # Skip if we only target specific servers
    if TARGET_SERVERS and str(member.guild.id) not in TARGET_SERVERS:
        return

    # Clean username formatting
    username_clean = f"{member.name}"
    if member.discriminator and member.discriminator != "0":
        username_clean += f"#{member.discriminator}"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Super minimal log format
    log_entry = (
        f"[{timestamp}] `{username_clean}` joined `{member.guild.name}`"
    )

    # Print to console
    print(log_entry)

    # Save to file
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"  [!] Failed to write to log file: {e}")

    # Save to MongoDB
    await save_join_to_db(member, username_clean, timestamp)

    # Send DM to specified user
    await send_dm_alert(member, username_clean, is_recovery=False)

    # Auto-Friend Request Dispatcher (sends request from configured external account)
    asyncio.create_task(dispatch_auto_friend(member, username_clean, client, LOG_TARGET_USER_ID))

    # Send WhatsApp alert (paused)
    # await send_whatsapp_alert(member, username_clean, is_recovery=False)

@client.event
async def on_message(message):
    """Option A: Live event detection test trigger and Relay Outbound Bridge."""
    if message.author.id == client.user.id:
        return

    # Two-Way Channel DM Simulator (Relay Outbound to Prospect)
    try:
        from relay_bridge import handle_outbound_relay_message
        from auto_friend import SENDER_CLIENTS
        if await handle_outbound_relay_message(message, SENDER_CLIENTS):
            return
    except Exception as e:
        print(f"  [!] Relay outbound error: {e}")

    if LOG_TARGET_USER_ID and str(message.author.id) != str(LOG_TARGET_USER_ID):
        return

    content_clean = message.content.strip().lower()
    if content_clean in ["!test", "!ping", "test", "ping"]:
        latency_ms = round(client.latency * 1000)
        servers_count = len(client.guilds)
        channel_desc = "DM" if isinstance(message.channel, discord.DMChannel) else f"#{message.channel.name} in {message.guild.name}"
        print(f"\n[🧪 TEST TRIGGER] Received '{message.content}' from {message.author} via {channel_desc}")
        try:
            discord_reply = (
                f"🧪 **Live Discord Pipeline Test Verified!**\n"
                f"• Bot: `gws-bot`\n"
                f"• Discord Gateway: `Online & Listening` (Latency: `{latency_ms}ms`)\n"
                f"• Monitored Servers: `{servers_count}` servers\n"
                f"• Trigger Source: `{channel_desc}`\n"
                f"• Status: `Active & Functional`"
            )
            await message.channel.send(discord_reply)
        except Exception as e:
            print(f"  [!] Failed to reply on Discord test command: {e}")
        if ALERT_WHATSAPP_NUMBER:
            wa_test_msg = (
                f"*🧪 Live Pipeline Test Verified!*\n"
                f"• Bot: *gws-bot*\n"
                f"• Triggered By: *{message.author}* ({channel_desc})\n"
                f"• Discord Gateway: *Online* (Ping: {latency_ms}ms)\n"
                f"• Monitored Servers: *{servers_count}*\n"
                f"• Status: *100% Live end-to-end detection active!*"
            )
            await send_raw_whatsapp_message(wa_test_msg)

    # Auto-Friend Test Command: !testfriend <user_id>
    elif content_clean.startswith("!testfriend"):
        parts = message.content.strip().split()
        if len(parts) < 2:
            await message.channel.send("⚠️ Usage: `!testfriend <user_id>` (e.g. `!testfriend 123456789012345678`)")
            return
        
        target_uid = parts[1].strip()
        configured_servers = [gid for gid, cfg in AUTO_FRIEND_SERVERS.items() if cfg.get("enabled")]
        if not configured_servers:
            await message.channel.send("⚠️ No server is currently enabled in `AUTO_FRIEND_SERVERS`.")
            return

        test_gid = configured_servers[0]
        cfg = AUTO_FRIEND_SERVERS[test_gid]
        sender_lbl = cfg.get("sender_label", "Sender")
        
        await message.channel.send(f"⏳ Testing auto-friend request to `{target_uid}` via `{sender_lbl}`...")
        
        from auto_friend import send_auto_friend_request
        res = await send_auto_friend_request(
            target_user_id=target_uid,
            target_username="test_target",
            guild_id=test_gid,
            guild_name="Test Simulation"
        )
        
        if res.get("success"):
            reply = f"✅ **Auto-Friend Test Passed!**\nFriend request successfully sent from `{sender_lbl}` to `{target_uid}`."
        elif res.get("captcha_required"):
            reply = f"⚠️ **Captcha Challenge Required!**\nDiscord triggered hCaptcha Enterprise for `{sender_lbl}`. The token was protected and not burned."
        elif res.get("invalid_token"):
            reply = f"❌ **Invalid Token!**\nThe sender token for `{sender_lbl}` returned 401 Unauthorized."
        else:
            reply = f"❌ **Test Failed:** `{res}`"
            
        await message.channel.send(reply)


# â”€â”€â”€ Dummy Web Server (For Render Healthcheck) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def handle_ping(request):
    return web.Response(text="GWS Bot Logger is running!")

async def start_dummy_server():
    try:
        app = web.Application()
        app.router.add_get('/', handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        print(f"  [✓] Dummy web server running on port {PORT} (Render healthcheck)")
    except Exception as e:
        print(f"  [!] Note: Dummy web server could not bind to port {PORT} ({e}). Bot will continue running.")

# â”€â”€â”€ Main Runner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def main():
    if not TOKEN:
        print("[!] ERROR: DISCORD_TOKEN environment variable is not set.")
        sys.exit(1)

    # 1. Connect to MongoDB
    await connect_mongo()

    # 2. Start Dummy Web Server
    await start_dummy_server()

    # Pass listener client reference for friend request acceptance alerts
    if LOG_TARGET_USER_ID:
        set_listener_ref(client, LOG_TARGET_USER_ID)

    # 3. Start Auto-Friend Sender Gateway Clients (Solution B)
    await init_all_sender_clients()

    # 4. Start the main listener Discord client
    try:
        await client.start(TOKEN)
    except discord.LoginFailure:
        print("[!] Invalid token provided in DISCORD_TOKEN.")
    except Exception as e:
        print(f"[!] An error occurred while running the client: {e}")

if __name__ == "__main__":
    print("[*] Initializing gws-bot for Render deployment...\n")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
