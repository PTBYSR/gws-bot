"""
honeypot_surveillance.py — Dedicated Honeypot Bot for Fake Admin & Scammer Detection.
Uses a dedicated Discord user token to catch fake admins, bots, and impersonators
as soon as they send inbound friend requests or DMs upon joining target servers.
"""
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
import discord
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

HONEYPOT_TOKEN = os.environ.get("HONEYPOT_TOKEN", "")
LOG_TARGET_USER_ID = os.environ.get("LOG_TARGET_USER_ID", "1551356562142928968")
HONEYPOT_ALERTS_FILE = os.path.join(os.path.dirname(__file__), "honeypot_alerts.json")
KING_TOKEN = os.environ.get("DISCORD_TOKEN")

client = discord.Client()

_RECENT_DETECTIONS = set()

# Server keyword mapping for instant fake admin attribution
KNOWN_STAFF_KEYWORDS = {
    "bird": ("BIRD GANG", "BirdGangCapital Fake Admin"),
    "herman": ("Herman Trading Premium", "Herman Fake Admin"),
    "hreman": ("Herman Trading Premium", "Herman Fake Admin"),
    "h2rman": ("Herman Trading Premium", "Herman Fake Admin"),
    "jonkoo": ("Jonkoo's Lounge", "Jonkoo Fake Admin"),
    "j0nk": ("Jonkoo's Lounge", "Jonkoo Fake Admin"),
    "tradermir": ("Trader Mir", "Trader Mir Fake Admin"),
    "gexoption": ("GEX Options Trading", "GEX Options Fake Admin"),
    "juicy": ("Juicy Tradez", "Juicy Tradez Fake Admin"),
    "xavier": ("Juicy Tradez", "Juicy Tradez Fake Admin"),
    "tamir": ("Fibonacci Traders", "Tamir Fibonacci Fake Admin"),
    "fibonacci": ("Fibonacci Traders", "Tamir Fibonacci Fake Admin"),
    "esmoney": ("🤑ES Money Printer🤑", "ES Money Printer Fake Admin"),
    "jdk": ("Tradingfloor by JDK / PAYTIENCE", "JDK Fake Admin"),
    "the_jdk": ("Tradingfloor by JDK / PAYTIENCE", "JDK Fake Admin"),
    "ptgambler": ("PtGambler TradingView Indicators", "PtGambler Fake Admin"),
    "platsn": ("PtGambler TradingView Indicators", "PtGambler Fake Admin"),
    "luke": ("Capital / Trading Community", "Luke Fake Admin"),
    "sheep": ("Trading Community", "SheepMeister Fake Admin"),
    "haikhuu": ("Haikhuu", "Allen Tran / Haikhuu Fake Admin"),
    "rjktrades": ("RJK Trades", "RJK Trades Fake Admin"),
    "seanlala": ("Mylol Trading Community", "Seanlala Fake Admin"),
}

def attribute_fake_admin(username: str, global_name: str, guild_names: list):
    """Detect which server a scammer or bot is impersonating."""
    combined = f"{username} {global_name or ''}".lower()
    
    # 1. Direct keyword match against known admins
    for kw, (srv, role) in KNOWN_STAFF_KEYWORDS.items():
        if kw in combined:
            return srv, role
            
    # 2. Check if username matches any joined server name
    for gname in guild_names:
        clean_gname = "".join(c for c in gname.lower() if c.isalnum())
        clean_user = "".join(c for c in combined if c.isalnum())
        if clean_gname and (clean_gname in clean_user or clean_user in clean_gname):
            return gname, f"Server Impersonator ({gname})"
            
    # 3. Check for generic staff keywords
    if any(k in combined for k in ["admin", "support", "mod", "official", "manager", "staff", "desk"]):
        return "Joined Server (Cross-Server)", "Generic Staff Impersonator"
        
    return "Unknown / Organic User", "Inbound Friend Request"

def send_operator_dm(content: str):
    """Disabled completely by user request. Does not send any DMs."""
    return

def record_alert(alert_text: str):
    """Save alert to file and console."""
    print(f"\n[🚨 HONEYPOT ALERT] {alert_text}", flush=True)
    try:
        alerts = []
        if os.path.exists(HONEYPOT_ALERTS_FILE):
            with open(HONEYPOT_ALERTS_FILE, "r", encoding="utf-8") as f:
                alerts = json.load(f)
        alerts.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert": alert_text
        })
        with open(HONEYPOT_ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts[-200:], f, indent=2)
    except Exception as e:
        print(f"  [!] Failed to save alert to file: {e}")
    send_operator_dm(alert_text)

@client.event
async def on_ready():
    print(f"============================================================", flush=True)
    print(f"  [🛡️] Honeypot Surveillance Active: @{client.user.name} ({client.user.id})", flush=True)
    print(f"  [+] Monitoring {len(client.guilds)} servers for inbound fake admins", flush=True)
    print(f"============================================================", flush=True)

@client.event
async def on_guild_join(guild):
    """Fires when the honeypot joins a new target server."""
    join_msg = f"📥 **Honeypot Joined New Server**: `{guild.name}` ({guild.id}) — Watching for inbound fake admins..."
    record_alert(join_msg)

@client.event
async def on_relationship_add(relationship):
    """Fires when an incoming friend request is received."""
    if relationship.type == discord.RelationshipType.incoming_request:
        user = relationship.user
        dedup_key = f"rel:{user.id}"
        if dedup_key in _RECENT_DETECTIONS:
            return
        _RECENT_DETECTIONS.add(dedup_key)

        guild_names = [g.name for g in client.guilds]
        server_attributed, role = attribute_fake_admin(user.name, user.global_name, guild_names)

        alert_msg = (
            f"🚨 **FAKE ADMIN INBOUND DETECTED!**\n"
            f"• **Attributed Server**: `{server_attributed}`\n"
            f"• **Role/Target**: `{role}`\n"
            f"• **Fake Admin**: @{user.name} ({user.global_name or 'No display name'})\n"
            f"• **User ID**: `{user.id}`\n"
            f"👉 https://discord.com/users/{user.id}"
        )
        record_alert(alert_msg)

@client.event
async def on_message(message):
    """Fires when an inbound DM is received."""
    if message.guild is None and message.author.id != client.user.id and not message.author.bot:
        dedup_key = f"msg:{message.author.id}"
        if dedup_key in _RECENT_DETECTIONS:
            return
        _RECENT_DETECTIONS.add(dedup_key)

        guild_names = [g.name for g in client.guilds]
        server_attributed, role = attribute_fake_admin(message.author.name, message.author.global_name, guild_names)

        alert_msg = (
            f"💬 **INBOUND DM FROM FAKE ADMIN!**\n"
            f"• **Attributed Server**: `{server_attributed}`\n"
            f"• **Sender**: @{message.author.name} ({message.author.global_name or 'N/A'})\n"
            f"• **Content**: \"{message.content[:200]}\"\n"
            f"👉 https://discord.com/users/{message.author.id}"
        )
        record_alert(alert_msg)

if __name__ == "__main__":
    try:
        client.run(HONEYPOT_TOKEN)
    except KeyboardInterrupt:
        print("\nHoneypot stopped.")
