"""
dashboard.py — Real-Time Fleet Control Dashboard & API.
Exposes a live web interface and JSON API on the Render web instance.
"""
import os
import json
import asyncio
import urllib.request
import urllib.error
import datetime
import base64
from aiohttp import web
from auto_friend_config import BATCH_1_SERVERS, BATCH_2_SERVERS, SERVICE_BATCH, _dec

# Reference to mongo db instance (set by main.py)
_DB = None
_LISTENER_CLIENT = None
_SENDER_CLIENTS = None

def set_dashboard_refs(db_ref, listener_client_ref=None, sender_clients_ref=None):
    global _DB, _LISTENER_CLIENT, _SENDER_CLIENTS
    _DB = db_ref
    _LISTENER_CLIENT = listener_client_ref
    _SENDER_CLIENTS = sender_clients_ref

# Complete inventory of the 14 fleet accounts mapped
FLEET_INVENTORY = [
    {
        "account": "king_arthur0001",
        "email": "kingarthur166289@gmail.com",
        "assigned_server": "Central Gateway Hub & Logger",
        "guild_id": "1561888167936659528",
        "batch": "Hub",
        "role": "Central Gateway Logger",
        "token_env": "DISCORD_TOKEN",
        "default_token": _dec("TVRVMU1UTTBNRGcyTkRZM09UVTBOWGcxT1EuR3ZHa3ZkLks1cnZFMXNvYmpDemEKck0wVWNGUkNwOEFuTjE0Y09rVG9qS1E0")
    },
    {
        "account": "allen.warfield.",
        "email": "georgemorcos.live1@gmail.com",
        "assigned_server": "Cryptex Commonwealth",
        "guild_id": "329712211989889026",
        "batch": "Batch 1",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk1USTNPRFl3T0RjNE1EQTBNak0zTXcuR1NXdmhJLlQycVJUR2dSRU14blQ4N0NvbTZEaFZGeUp4THBWQlpNeWlDXzBR")
    },
    {
        "account": "coins.ph_hdawg.",
        "email": "rams.eytn.wdeborah1955@gmail.com",
        "assigned_server": "Coins Community",
        "guild_id": "974604371860021289",
        "batch": "Batch 1",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRJME9ESTBNelkwTURJMk1qZzFOamMyTlEuR2ZxUXZFLnRMelVMWkgwbHI1UzVqdEw5ZFcwbW5lZjRrcDRIVFV0azc2R1Zr")
    },
    {
        "account": "talon.1977._",
        "email": "pasetechnologies@gmail.com",
        "assigned_server": "Underground Trading Company",
        "guild_id": "958180490957975612",
        "batch": "Batch 1",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRNeU16UXlOakF3TWpFd05USTNNRFF3TXcuR2lRR1JXLm9WTU8wamhqSVF4MmFOOXhwMUFMY1JTV29vLXo1RXN2RURCVVpr")
    },
    {
        "account": "themaster._5",
        "email": "samuelderrick081@gmail.com",
        "assigned_server": "DVLT Underground",
        "guild_id": "1433212223970345043",
        "batch": "Batch 1",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk16WTBORGt4T1RVeE1EUTNNRGMyTWcuR0prc3NmLlYzeHQzTkRTQlJYdlZ4SkF1NkJiVGZNUXFZdXBlOElIY0pPd3hN")
    },
    {
        "account": "official___rjktrades",
        "email": "albertflemming000@gmail.com",
        "assigned_server": "RJK Trades",
        "guild_id": "1432925421145686028",
        "batch": "Batch 1",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk16WTJPVGN6TXpjd05EY3pNamM0TncuR19tWDd1LjI4MkhSSk1reDFDQ2RUNXMyWDlmdE5TWGZ3SmhIWXM4SzFhMzlZ")
    },
    {
        "account": "brendan.guastaferro._",
        "email": "alvinmaduka@gmail.com",
        "assigned_server": "Liquidity Theory",
        "guild_id": "1297957813644951613",
        "batch": "Batch 2",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk1qa3dPRGt4TmpZd09EWTJNelU1TlEuRzlfcEEwLnA1dEpDYl9zMTNxZVBuVG4zY2VNSlhJRGt0VmZkM0pEbmVuWFpv")
    },
    {
        "account": "rhu.wan",
        "email": "info@murdochvault.com",
        "assigned_server": "PAYTIENCE",
        "guild_id": "1306399620217438309",
        "batch": "Batch 2",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk1qa3lPVEExTkRVeE9UTTVORFF3TncuR1lMTllBLjdOR3UwOE00dFZ0SE14OG1jQUZ1eElmSlRXQjQxZ2JuNkl1QXI0")
    },
    {
        "account": "ecsadmin_",
        "email": "meldridwilson@gmail.com",
        "assigned_server": "Web-Based Wealth",
        "guild_id": "1069351223217635428",
        "batch": "Batch 2",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk16SXdOVEkyT1RJek1EUTFOamt4TXcuR0t3bDhhLjZ1ZGQ5Z2dBVFpkeFpuU3pBWFRRLUJYX2pfaFNoZ1I4b0FNcFZB")
    },
    {
        "account": "seanlala._",
        "email": "samuelbankz2144@gmail.com",
        "assigned_server": "Mylol Trading Community",
        "guild_id": "828801846277308426",
        "batch": "Batch 2",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk16WTNNelkwTURneE1qSTRNakEwT0EuR0hOaWhrLk5RM1NGNzhpU2xQZGxxcFFDQnVqQW50MlZvY3JMRkxjQ1FEVmVr")
    },
    {
        "account": "iam.vk7._",
        "email": "info@westcorevault.com",
        "assigned_server": "Trading University",
        "guild_id": "1122865043952898128",
        "batch": "Batch 2",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk1qa3pNekF3TWpZeU1UZ3lNRGszT1EuR1Nzbk5ZLk5uUHZ0Rm5ib0tUYjQ0c045Szh1MUcxOVJlZmRRUGlTeUplNHdV")
    },
    {
        "account": "nicliu___",
        "email": "nicliu236@gmail.com",
        "assigned_server": "PASE",
        "guild_id": "1330889066425749576",
        "batch": "Batch 2",
        "role": "Automated Account Listener",
        "default_token": _dec("TVRVMk1UWTVNalV3TXpBM01qTXhNek0yTlEuR1lKUVBkLkU1YWRxb1JXdGRtQ2FkX1pONDZvWUdGcVAzYmlmQU05Z2Nja1c0")
    },
    {
        "account": "adem__82099",
        "email": "claireguerita@gmail.com",
        "assigned_server": "Verified Wealth",
        "guild_id": "1334980338467733596",
        "batch": "Manual Add",
        "role": "⚡ Fast Operator Manual Add",
        "default_token": _dec("TVRBeE1ERXdPRFl3TURRME16YzBNREl5TUEuR0lBaG9QLmRoQ1lzenFJbTlKeXBWOE5XazFIYTlBNlB4QXE0Y2RuWXJiU0hn")
    },
    {
        "account": "horizon.trading",
        "email": "kyliandickson900@gmail.com",
        "assigned_server": "Horizon Trading",
        "guild_id": "563389318773604382",
        "batch": "Manual Add",
        "role": "⚡ Fast Operator Manual Add",
        "default_token": _dec("TVRVMk16RTVPRFF5TVRFek1UVTVOVGt4TncuR0Fmc2RYLllCclBxWlB6TXYyclBsdDJSQmd2ZWxuSGVKMWphVDdONTRsQ3N3")
    }
]

def format_relative_time(dt_val):
    """
    Format time:
    - If < 1 hour: 'Xm ago'
    - If < 24 hours: 'Xh ago'
    - If < 7 days: 'Xd ago'
    - If >= 7 days (1 week or more): 'Mon DD, YYYY' normal date format
    """
    if not dt_val:
        return "No joins recorded"
    
    if isinstance(dt_val, str):
        try:
            dt = datetime.datetime.fromisoformat(dt_val.replace('Z', '+00:00'))
        except Exception:
            return dt_val[:10]
    else:
        dt = dt_val

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    diff = now - dt

    seconds = int(diff.total_seconds())
    if seconds < 0:
        seconds = 0
        
    minutes = int(seconds / 60)
    hours = int(minutes / 60)
    days = int(hours / 24)

    if days >= 7:
        # 1 week or more: normal date format
        return dt.strftime("%b %d, %Y")
    elif days >= 1:
        hours_rem = hours % 24
        return f"{days}d {hours_rem}h ago" if hours_rem > 0 else f"{days}d ago"
    elif hours >= 1:
        mins_rem = minutes % 60
        return f"{hours}h {mins_rem}m ago" if mins_rem > 0 else f"{hours}h ago"
    elif minutes >= 1:
        return f"{minutes}m ago"
    else:
        return "Just now (<1m ago)"

def format_interval(dt_last, dt_second_last):
    """Calculate and format time between 2nd-to-last join and last join."""
    if not dt_last or not dt_second_last:
        return "N/A (insufficient data)"
    try:
        if isinstance(dt_last, str):
            dt_last = datetime.datetime.fromisoformat(dt_last.replace('Z', '+00:00'))
        if isinstance(dt_second_last, str):
            dt_second_last = datetime.datetime.fromisoformat(dt_second_last.replace('Z', '+00:00'))
            
        diff = dt_last - dt_second_last
        total_seconds = int(abs(diff.total_seconds()))
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        mins = (total_seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        if mins > 0 and days == 0:
            parts.append(f"{mins}m")
            
        return " ".join(parts) if parts else "< 1m"
    except Exception:
        return "N/A"

async def get_server_joins_from_db_or_file(guild_id: str, server_name: str):
    """Fetch the latest joins for a specific server from MongoDB or fallback to logs/joins.log."""
    joins = []
    
    # 1. Try Mongo
    if _DB is not None:
        try:
            cursor = _DB.joins.find({"guild_id": str(guild_id)}).sort("joined_at", -1).limit(5)
            db_joins = await cursor.to_list(length=5)
            for j in db_joins:
                joins.append({
                    "username": j.get("username", "Unknown"),
                    "joined_at": j.get("joined_at") or j.get("logged_at")
                })
        except Exception:
            pass

    # 2. Fallback to logs/joins.log if empty
    if not joins:
        log_path = os.path.join(os.path.dirname(__file__), "logs", "joins.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    if f"` joined `{server_name}`" in line or f"joined `{server_name}`" in line:
                        # Extract date: [2026-10-18 19:43:37] `username` joined `Server`
                        try:
                            ts_str = line[1:20]
                            dt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                            u_part = line.split("`")[1] if "`" in line else "Unknown"
                            joins.append({"username": u_part, "joined_at": dt})
                            if len(joins) >= 5:
                                break
                        except Exception:
                            pass
            except Exception:
                pass

    last_join = joins[0]["joined_at"] if len(joins) > 0 else None
    second_last = joins[1]["joined_at"] if len(joins) > 1 else None
    interval_str = format_interval(last_join, second_last) if last_join and second_last else "N/A"

    return {
        "last_join_formatted": format_relative_time(last_join),
        "last_join_raw": last_join.isoformat() if isinstance(last_join, datetime.datetime) else None,
        "second_last_interval": interval_str,
        "recent_joins": [
            {
                "username": j["username"],
                "time_formatted": format_relative_time(j["joined_at"])
            }
            for j in joins
        ]
    }

async def handle_fleet_api(request):
    """JSON API returning full fleet state with join metrics."""
    data = []
    current_active_batch = SERVICE_BATCH

    for item in FLEET_INVENTORY:
        gid = item["guild_id"]
        sname = item["assigned_server"]
        join_stats = await get_server_joins_from_db_or_file(gid, sname)

        # Determine real-time status label
        batch = item["batch"]
        if batch == "Hub":
            status_text = "🟢 Active (Central Hub)"
            status_code = "hub"
        elif batch == "Batch 1":
            status_text = "🟢 Active (Batch 1)" if current_active_batch == "1" else "🟡 Configured (Batch 1)"
            status_code = "batch_1"
        elif batch == "Batch 2":
            status_text = "🟢 Active (Batch 2)" if current_active_batch == "2" else "🟡 Configured (Batch 2)"
            status_code = "batch_2"
        elif batch == "Manual Add":
            status_text = "⚡ Manual Fast-Add"
            status_code = "manual"
        else:
            status_text = "⚪ Unassigned"
            status_code = "unassigned"

        data.append({
            "account": item["account"],
            "email": item["email"],
            "assigned_server": sname,
            "guild_id": gid,
            "batch": batch,
            "role": item["role"],
            "status": status_text,
            "status_code": status_code,
            "last_join": join_stats["last_join_formatted"],
            "second_last_interval": join_stats["second_last_interval"],
            "recent_joins": join_stats["recent_joins"]
        })

    return web.json_response({
        "success": True,
        "active_service_batch": current_active_batch,
        "total_accounts": len(data),
        "fleet": data
    })

async def handle_test_token_api(request):
    """Test token validity live against Discord API."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    target_account = body.get("account")
    
    # Locate token for this account
    found_item = next((x for x in FLEET_INVENTORY if x["account"] == target_account), None)
    if not found_item:
        return web.json_response({"success": False, "error": "Account not found in inventory"}, status=404)

    token = os.environ.get(found_item.get("token_env", "")) or found_item.get("default_token")
    if not token:
        return web.json_response({"success": False, "error": "No token found for account"}, status=400)

    # Perform live test
    start_t = asyncio.get_event_loop().time()
    headers = {
        "Authorization": token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        # 1. Fetch user @me
        req = urllib.request.Request("https://discord.com/api/v9/users/@me", headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            u_data = json.loads(resp.read().decode("utf-8"))
        latency_ms = round((asyncio.get_event_loop().time() - start_t) * 1000)

        # 2. Check guild presence
        in_target = False
        guild_count = 0
        try:
            req_g = urllib.request.Request("https://discord.com/api/v9/users/@me/guilds", headers=headers)
            with urllib.request.urlopen(req_g, timeout=8) as resp_g:
                guilds = json.loads(resp_g.read().decode("utf-8"))
                guild_count = len(guilds)
                target_gid = str(found_item.get("guild_id"))
                in_target = any(str(g.get("id")) == target_gid for g in guilds)
        except Exception:
            pass

        return web.json_response({
            "success": True,
            "valid": True,
            "account": target_account,
            "username": u_data.get("username"),
            "display_name": u_data.get("global_name") or u_data.get("username"),
            "user_id": u_data.get("id"),
            "email": u_data.get("email"),
            "latency_ms": latency_ms,
            "guild_count": guild_count,
            "in_assigned_server": in_target,
            "assigned_server": found_item.get("assigned_server")
        })

    except urllib.error.HTTPError as e:
        latency_ms = round((asyncio.get_event_loop().time() - start_t) * 1000)
        return web.json_response({
            "success": True,
            "valid": False,
            "account": target_account,
            "status_code": e.code,
            "latency_ms": latency_ms,
            "error": f"Discord returned HTTP {e.code} (Unauthorized / Invalid Token)" if e.code == 401 else f"HTTP {e.code}"
        })
    except Exception as e:
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def handle_dashboard_page(request):
    """Serve the minimal live responsive Fleet Control Dashboard HTML."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GWS Fleet Control Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111726;
      --card-border: #1e293b;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --green: #10b981;
      --amber: #f59e0b;
      --red: #ef4444;
      --drawer-bg: #0f172a;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      padding: 1.25rem 2rem;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(17, 23, 38, 0.7);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 20;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .brand-icon {
      width: 34px;
      height: 34px;
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 1.1rem;
    }
    .brand-title {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .brand-sub {
      font-size: 0.78rem;
      color: var(--text-muted);
    }
    .header-pills {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.35rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      background: #1e293b;
      color: var(--text-muted);
      border: 1px solid var(--card-border);
    }
    .badge-live {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border-color: rgba(16, 185, 129, 0.3);
    }
    .pulse-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
    }
    main {
      padding: 2rem;
      max-width: 1280px;
      margin: 0 auto;
      width: 100%;
      flex: 1;
    }
    .table-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.88rem;
    }
    th {
      padding: 1rem 1.25rem;
      background: rgba(15, 23, 42, 0.6);
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--card-border);
      text-transform: uppercase;
      font-size: 0.72rem;
      letter-spacing: 0.05em;
    }
    td {
      padding: 1rem 1.25rem;
      border-bottom: 1px solid rgba(30, 41, 59, 0.6);
      vertical-align: middle;
    }
    tr:last-child td { border-bottom: none; }
    tr.fleet-row {
      transition: background 0.15s ease;
      cursor: pointer;
    }
    tr.fleet-row:hover {
      background: rgba(30, 41, 59, 0.4);
    }
    .account-cell {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      font-weight: 600;
      color: #fff;
    }
    .avatar-placeholder {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: #1e293b;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.75rem;
      color: var(--accent);
      border: 1px solid var(--card-border);
    }
    .email-cell {
      color: var(--text-muted);
      font-family: monospace;
      font-size: 0.82rem;
    }
    .server-tag {
      font-weight: 500;
      color: #e2e8f0;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      padding: 0.25rem 0.65rem;
      border-radius: 6px;
      font-size: 0.76rem;
      font-weight: 600;
    }
    .status-hub { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .status-batch1 { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .status-batch2 { background: rgba(139, 92, 246, 0.15); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); }
    .status-manual { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .gear-btn {
      background: transparent;
      border: 1px solid var(--card-border);
      border-radius: 6px;
      color: var(--text-muted);
      padding: 0.4rem 0.6rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
      font-size: 0.85rem;
    }
    .gear-btn:hover {
      background: #1e293b;
      color: #fff;
      border-color: #3b82f6;
    }
    /* Side Drawer Overlay & Panel */
    .drawer-overlay {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(0, 0, 0, 0.65);
      backdrop-filter: blur(4px);
      z-index: 50;
      opacity: 0;
      visibility: hidden;
      transition: all 0.25s ease;
    }
    .drawer-overlay.active {
      opacity: 1;
      visibility: visible;
    }
    .drawer-panel {
      position: fixed;
      top: 0;
      right: 0;
      width: 420px;
      max-width: 90vw;
      height: 100vh;
      background: var(--drawer-bg);
      border-left: 1px solid var(--card-border);
      z-index: 60;
      transform: translateX(100%);
      transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
      box-shadow: -10px 0 40px rgba(0,0,0,0.5);
    }
    .drawer-panel.active {
      transform: translateX(0);
    }
    .drawer-header {
      padding: 1.5rem;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .drawer-title {
      font-size: 1.1rem;
      font-weight: 700;
    }
    .close-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 1.25rem;
      line-height: 1;
      padding: 0.25rem;
      border-radius: 4px;
    }
    .close-btn:hover { color: #fff; }
    .drawer-body {
      padding: 1.5rem;
      overflow-y: auto;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }
    .section-box {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 1.15rem;
    }
    .section-title {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.85rem;
    }
    .prop-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.6rem;
      font-size: 0.84rem;
    }
    .prop-label { color: var(--text-muted); }
    .prop-val { font-weight: 600; color: #fff; }
    .btn-test {
      width: 100%;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 0.75rem;
      font-weight: 600;
      font-size: 0.88rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      transition: background 0.15s ease;
    }
    .btn-test:hover { background: var(--accent-hover); }
    .btn-test:disabled { opacity: 0.6; cursor: not-allowed; }
    .test-result-box {
      margin-top: 0.75rem;
      padding: 0.85rem;
      border-radius: 8px;
      font-size: 0.82rem;
      line-height: 1.4;
      display: none;
    }
    .test-result-valid {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
    }
    .test-result-invalid {
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: #f87171;
    }
    .metric-badge {
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
      margin-bottom: 0.5rem;
    }
    .metric-num {
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
    }
    .recent-join-item {
      padding: 0.4rem 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      font-size: 0.8rem;
      display: flex;
      justify-content: space-between;
    }
    .recent-join-item:last-child { border-bottom: none; }
    .spinner {
      width: 14px;
      height: 14px;
      border: 2px solid rgba(255,255,255,0.3);
      border-radius: 50%;
      border-top-color: #fff;
      animation: spin 0.8s ease-in-out infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-icon">⚡</div>
      <div>
        <div class="brand-title">GWS Fleet Control</div>
        <div class="brand-sub">Real-Time Account Listeners & Servers Dashboard</div>
      </div>
    </div>
    <div class="header-pills">
      <span class="badge badge-live"><span class="pulse-dot"></span> Live Fleet</span>
      <span class="badge" id="serviceBatchBadge">Loading...</span>
      <span class="badge" id="accountCountBadge">14 Accounts</span>
    </div>
  </header>

  <main>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Account Username</th>
            <th>Attached Email</th>
            <th>Assigned Target Server</th>
            <th>Status</th>
            <th style="text-align: center;">Actions</th>
          </tr>
        </thead>
        <tbody id="fleetTableBody">
          <tr>
            <td colspan="5" style="text-align: center; padding: 3rem; color: var(--text-muted);">
              Connecting to live fleet state...
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </main>

  <!-- Side Drawer Details & Testing Panel -->
  <div class="drawer-overlay" id="drawerOverlay" onclick="closeDrawer()"></div>
  <div class="drawer-panel" id="drawerPanel">
    <div class="drawer-header">
      <div class="drawer-title" id="drawerAccountTitle">Account Details</div>
      <button class="close-btn" onclick="closeDrawer()">✕</button>
    </div>
    <div class="drawer-body">

      <!-- Account & Server Info Card -->
      <div class="section-box">
        <div class="section-title">Assignment Information</div>
        <div class="prop-row">
          <span class="prop-label">Username:</span>
          <span class="prop-val" id="dUsername">-</span>
        </div>
        <div class="prop-row">
          <span class="prop-label">Attached Email:</span>
          <span class="prop-val" id="dEmail">-</span>
        </div>
        <div class="prop-row">
          <span class="prop-label">Target Server:</span>
          <span class="prop-val" id="dServer">-</span>
        </div>
        <div class="prop-row">
          <span class="prop-label">Guild ID:</span>
          <span class="prop-val" id="dGuildId" style="font-family: monospace;">-</span>
        </div>
        <div class="prop-row">
          <span class="prop-label">Fleet Batch:</span>
          <span class="prop-val" id="dBatch">-</span>
        </div>
        <div class="prop-row">
          <span class="prop-label">Operational Mode:</span>
          <span class="prop-val" id="dRole" style="font-size: 0.8rem;">-</span>
        </div>
      </div>

      <!-- Live Token Health Ping -->
      <div class="section-box">
        <div class="section-title">Token Live Health Ping</div>
        <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.85rem;">
          Ping Discord Gateway API live to test token authentication, roundtrip latency, and guild presence.
        </p>
        <button class="btn-test" id="btnTestToken" onclick="runLiveTokenTest()">
          <span id="btnTestText">⚡ Run Live Discord Ping</span>
        </button>
        <div class="test-result-box" id="testResultBox"></div>
      </div>

      <!-- Join Frequency & Interval Stats -->
      <div class="section-box">
        <div class="section-title">Friend Request & Join Activity</div>
        
        <div style="margin-bottom: 1rem;">
          <span class="prop-label" style="font-size: 0.75rem;">LAST MEMBER JOINED (FRIEND REQUEST TARGET):</span>
          <div class="metric-badge" style="margin-top: 0.25rem;">
            <div class="metric-num" id="dLastJoin">-</div>
          </div>
        </div>

        <div style="margin-bottom: 1rem;">
          <span class="prop-label" style="font-size: 0.75rem;">TIME BETWEEN 2ND-TO-LAST & LAST JOIN:</span>
          <div class="metric-badge" style="margin-top: 0.25rem;">
            <div class="metric-num" id="dInterval" style="font-size: 1.05rem; color: #cbd5e1;">-</div>
          </div>
        </div>

        <div>
          <span class="prop-label" style="font-size: 0.75rem;">RECENT PROSPECT JOINS:</span>
          <div id="dRecentJoinsList" style="margin-top: 0.5rem;">
            <div style="color: var(--text-muted); font-size: 0.8rem;">No recent joins recorded.</div>
          </div>
        </div>

      </div>

    </div>
  </div>

  <script>
    let currentFleetData = [];
    let selectedAccount = null;

    async function loadFleet() {
      try {
        const res = await fetch('/api/fleet');
        const data = await res.json();
        if (data.success) {
          currentFleetData = data.fleet;
          document.getElementById('serviceBatchBadge').textContent = 'Service ' + (data.active_service_batch === '2' ? 'Batch 2' : 'Batch 1');
          document.getElementById('accountCountBadge').textContent = data.total_accounts + ' Accounts';
          renderTable(data.fleet);
        }
      } catch (err) {
        console.error('Failed to load fleet data:', err);
      }
    }

    function renderTable(fleet) {
      const tbody = document.getElementById('fleetTableBody');
      tbody.innerHTML = '';

      fleet.forEach((item, index) => {
        const tr = document.createElement('tr');
        tr.className = 'fleet-row';
        tr.onclick = (e) => {
          if (!e.target.closest('.gear-btn')) openDrawer(index);
        };

        let badgeClass = 'status-hub';
        if (item.status_code === 'batch_1') badgeClass = 'status-batch1';
        else if (item.status_code === 'batch_2') badgeClass = 'status-batch2';
        else if (item.status_code === 'manual') badgeClass = 'status-manual';

        tr.innerHTML = `
          <td>
            <div class="account-cell">
              <div class="avatar-placeholder">${item.account.charAt(0).toUpperCase()}</div>
              <div>${item.account}</div>
            </div>
          </td>
          <td class="email-cell">${item.email}</td>
          <td><span class="server-tag">${item.assigned_server}</span></td>
          <td>
            <span class="status-pill ${badgeClass}">${item.status}</span>
          </td>
          <td style="text-align: center;">
            <button class="gear-btn" onclick="openDrawer(${index})" title="View Details & Test">
              ⚙️ More Info
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function openDrawer(index) {
      const item = currentFleetData[index];
      if (!item) return;
      selectedAccount = item;

      document.getElementById('drawerAccountTitle').textContent = item.account;
      document.getElementById('dUsername').textContent = item.account;
      document.getElementById('dEmail').textContent = item.email;
      document.getElementById('dServer').textContent = item.assigned_server;
      document.getElementById('dGuildId').textContent = item.guild_id || 'N/A';
      document.getElementById('dBatch').textContent = item.batch;
      document.getElementById('dRole').textContent = item.role;

      document.getElementById('dLastJoin').textContent = item.last_join || 'None';
      document.getElementById('dInterval').textContent = item.second_last_interval || 'N/A';

      const joinsList = document.getElementById('dRecentJoinsList');
      if (item.recent_joins && item.recent_joins.length > 0) {
        joinsList.innerHTML = item.recent_joins.map(j => `
          <div class="recent-join-item">
            <span style="font-weight: 500;">👤 ${j.username}</span>
            <span style="color: var(--text-muted);">${j.time_formatted}</span>
          </div>
        `).join('');
      } else {
        joinsList.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">No recent joins recorded.</div>';
      }

      // Reset test result box
      const resBox = document.getElementById('testResultBox');
      resBox.style.display = 'none';
      resBox.className = 'test-result-box';
      resBox.innerHTML = '';

      document.getElementById('drawerOverlay').classList.add('active');
      document.getElementById('drawerPanel').classList.add('active');
    }

    function closeDrawer() {
      document.getElementById('drawerOverlay').classList.remove('active');
      document.getElementById('drawerPanel').classList.remove('active');
    }

    async function runLiveTokenTest() {
      if (!selectedAccount) return;
      const btn = document.getElementById('btnTestToken');
      const text = document.getElementById('btnTestText');
      const resBox = document.getElementById('testResultBox');

      btn.disabled = true;
      text.innerHTML = '<span class="spinner"></span> Testing live token...';
      resBox.style.display = 'none';

      try {
        const response = await fetch('/api/test-token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account: selectedAccount.account })
        });
        const data = await response.json();

        resBox.style.display = 'block';
        if (data.valid) {
          resBox.className = 'test-result-box test-result-valid';
          resBox.innerHTML = `
            <strong>✅ Token 100% Valid & Authenticated!</strong><br>
            • Discord User: @${data.username} (${data.display_name})<br>
            • API Latency: <strong>${data.latency_ms}ms</strong><br>
            • Mutual Guilds: ${data.guild_count} server(s)<br>
            • Inside Assigned Server: <strong>${data.in_assigned_server ? 'Yes (Active Member)' : 'Not in server'}</strong>
          `;
        } else {
          resBox.className = 'test-result-box test-result-invalid';
          resBox.innerHTML = `
            <strong>❌ Token Failed / Unauthorized</strong><br>
            • Status: ${data.error || 'Invalid token (401)'}<br>
            • Latency: ${data.latency_ms || 0}ms
          `;
        }
      } catch (err) {
        resBox.style.display = 'block';
        resBox.className = 'test-result-box test-result-invalid';
        resBox.innerHTML = `<strong>❌ Request Failed:</strong> ${err.message}`;
      } finally {
        btn.disabled = false;
        text.textContent = '⚡ Run Live Discord Ping';
      }
    }

    // Initial load + refresh every 30s
    loadFleet();
    setInterval(loadFleet, 30000);
  </script>
</body>
</html>
"""
    return web.Response(text=html_content, content_type='text/html')

def setup_dashboard_routes(app: web.Application):
    """Register dashboard routes on the aiohttp application."""
    app.router.add_get('/', handle_dashboard_page)
    app.router.add_get('/dashboard', handle_dashboard_page)
    app.router.add_get('/health', lambda r: web.json_response({"status": "ok", "service": "gws-bot"}))
    app.router.add_get('/ping', lambda r: web.Response(text="GWS Bot Logger is running!"))
    app.router.add_get('/api/fleet', handle_fleet_api)
    app.router.add_post('/api/test-token', handle_test_token_api)
    print("  [✓] Dashboard & Live Fleet API routes registered on web server.")
