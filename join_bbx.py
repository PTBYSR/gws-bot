"""
Join the Blackboxstocks Discord server using the selfbot token.
Invite from recon: discord.com/invite/blackbox-stocks-stock-market-options-trading-dark-290278814217535489
"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("[!] DISCORD_TOKEN not set")
    exit(1)

INVITE_CODE = "blackbox-stocks-stock-market-options-trading-dark-290278814217535489"
TARGET_GUILD_ID = "290278814217535489"

HEADERS = {
    "Authorization": TOKEN,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "X-Super-Properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyNi4wLjAuMCBTYWZhcmkvNTM3LjM2Iiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIn0=",
}

# Step 1: Check if already in the guild
print("[*] Checking current guilds...")
r = requests.get("https://discord.com/api/v9/users/@me/guilds", headers=HEADERS)
if r.status_code == 200:
    guilds = r.json()
    for g in guilds:
        if g["id"] == TARGET_GUILD_ID:
            print(f"[✓] Already in Blackboxstocks server: {g['name']} (ID: {g['id']})")
            exit(0)
    print(f"[~] Not yet in Blackboxstocks. Currently in {len(guilds)} servers.")
else:
    print(f"[!] Failed to fetch guilds: {r.status_code} {r.text}")
    exit(1)

# Step 2: Preview the invite
print(f"\n[*] Previewing invite: {INVITE_CODE}...")
r_preview = requests.get(
    f"https://discord.com/api/v9/invites/{INVITE_CODE}?with_counts=true&with_expiration=true",
    headers=HEADERS
)
if r_preview.status_code == 200:
    invite_data = r_preview.json()
    guild_info = invite_data.get("guild", {})
    print(f"    Guild: {guild_info.get('name')} (ID: {guild_info.get('id')})")
    print(f"    Members: ~{invite_data.get('approximate_member_count')} | Online: ~{invite_data.get('approximate_presence_count')}")
    print(f"    Channel: #{invite_data.get('channel', {}).get('name')}")
else:
    print(f"[!] Failed to preview invite: {r_preview.status_code} {r_preview.text}")

# Step 3: Accept the invite (join the server)
print(f"\n[*] Accepting invite to join Blackboxstocks...")
r_join = requests.post(
    f"https://discord.com/api/v9/invites/{INVITE_CODE}",
    headers=HEADERS,
    json={}
)

if r_join.status_code in (200, 201):
    join_data = r_join.json()
    guild_joined = join_data.get("guild", {})
    print(f"[✓] SUCCESS! Joined: {guild_joined.get('name')} (ID: {guild_joined.get('id')})")
elif r_join.status_code == 204:
    print(f"[✓] SUCCESS! Joined Blackboxstocks (204 No Content)")
else:
    print(f"[!] Failed to join: {r_join.status_code}")
    print(f"    Response: {r_join.text}")

# Step 4: Verify membership
print(f"\n[*] Verifying membership...")
r_verify = requests.get("https://discord.com/api/v9/users/@me/guilds", headers=HEADERS)
if r_verify.status_code == 200:
    guilds = r_verify.json()
    for g in guilds:
        if g["id"] == TARGET_GUILD_ID:
            print(f"[✓] CONFIRMED in server: {g['name']} (ID: {g['id']})")
            break
    else:
        print("[!] Guild not found in guilds list after join attempt.")
        print("    This may mean the join is pending verification/screening.")
else:
    print(f"[!] Failed to verify: {r_verify.status_code}")
