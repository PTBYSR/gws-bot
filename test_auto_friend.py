"""
test_auto_friend.py — Quick test script to verify auto-friend functionality.

Usage:
  python test_auto_friend.py [target_user_id] [target_username]

If arguments are omitted, it prompts or tests with configured defaults.
"""
import sys
import asyncio
import os
from dotenv import load_dotenv

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from auto_friend import send_auto_friend_request
from auto_friend_config import AUTO_FRIEND_SERVERS

async def main():
    print("=" * 60)
    print("  Auto-Friend Request Dispatcher — Test Runner")
    print("=" * 60)

    # 1. Identify configured servers
    configured = {k: v for k, v in AUTO_FRIEND_SERVERS.items() if v.get("enabled")}
    
    if not configured:
        print("[!] No server is enabled in AUTO_FRIEND_SERVERS.")
        print("    Please set in .env:")
        print("      ENABLE_AUTO_FRIEND=true")
        print("      AUTO_FRIEND_SERVER_ID=<guild_id>")
        print("      AUTO_FRIEND_SENDER_TOKEN=<sender_user_token>")
        return

    guild_id, cfg = list(configured.items())[0]
    sender_label = cfg.get("sender_label", "Sender")
    print(f"[*] Active Configuration:")
    print(f"    • Target Guild ID : {guild_id}")
    print(f"    • Sender Account  : {sender_label}")
    print(f"    • Delay           : {cfg.get('delay_seconds')}s")
    print("=" * 60)

    # 2. Get target user
    if len(sys.argv) >= 3:
        target_id = sys.argv[1].strip()
        target_name = sys.argv[2].strip()
    else:
        target_id = input("Enter Discord User ID to send friend request to: ").strip()
        target_name = input("Enter Username (for display log): ").strip() or "test_user"

    if not target_id:
        print("[!] Target User ID is required.")
        return

    print(f"\n[*] Connecting sender account to Gateway (Solution B)...")
    from auto_friend import init_all_sender_clients
    await init_all_sender_clients()
    await asyncio.sleep(4)

    print(f"\n[*] Dispatching test friend request to {target_name} ({target_id})...")
    result = await send_auto_friend_request(
        target_user_id=target_id,
        target_username=target_name,
        guild_id=guild_id,
        guild_name="Test Simulation Server"
    )

    print("\n" + "=" * 60)
    print(f"[*] Result: {result}")
    if result.get("success"):
        print(f"[✓] Friend request successfully dispatched from {sender_label}!")
    elif result.get("captcha_required"):
        print(f"[!] Discord required Captcha for this account. Request paused safely.")
    elif result.get("invalid_token"):
        print(f"[!] The sender token is invalid or expired (401).")
    elif result.get("rate_limited"):
        print(f"[!] Sender account is rate limited (429).")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
