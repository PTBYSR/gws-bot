import os
import sys
import json
import re
import io
import time
import subprocess
import urllib.request
import urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

OPENCLI_PATH = r"C:\Users\paule\.agent-reach\tools\npm-global\opencli.cmd"

QUERIES = [
    '"discord.gg" "options trading"',
    '"discord.gg" "thetagang"',
    '"discord.gg" "swing trading" stock',
    '"discord.gg" "SPY" "options"',
    '"discord.gg" "stock alerts" -crypto',
    '"discord.gg" "options" "calls" "puts"',
    '"options trading" "discord server" invite',
    '"day trading" "options" "discord.gg"',
    '"stock market" "discord.gg" options'
]

INVITE_REGEX = re.compile(r'(?:https?://)?(?:www\.)?(?:discord\.gg/|discord(?:app)?\.com/invite/)([a-zA-Z0-9-]+)', re.IGNORECASE)
TCO_REGEX = re.compile(r'https?://t\.co/[a-zA-Z0-9]+', re.IGNORECASE)

def resolve_tco(tco_url):
    try:
        req = urllib.request.Request(tco_url, headers={'User-Agent': 'Mozilla/5.0'})
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
        resp = opener.open(req, timeout=4)
        return resp.geturl()
    except Exception:
        return None

def fetch_twitter_tweets(query, limit=20):
    print(f"[*] Searching Twitter for: {query} (limit {limit})...")
    cmd = [OPENCLI_PATH, "twitter", "search", query, "--limit", str(limit), "-f", "json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=35, cwd=r"c:\Users\paule\OneDrive\Desktop\Agent-Reach")
        if proc.returncode != 0:
            print(f"[-] Error querying Twitter for '{query}': {proc.stderr[:200]}")
            return []
        
        # opencli sometimes has update notices before JSON
        raw = proc.stdout.strip()
        start = raw.find('[')
        end = raw.rfind(']')
        if start != -1 and end != -1:
            json_str = raw[start:end+1]
            return json.loads(json_str)
        return []
    except Exception as e:
        print(f"[-] Exception running search '{query}': {e}")
        return []

def extract_invites_from_tweet(tweet):
    invites = set()
    text = tweet.get('text', '') or ''
    card = tweet.get('card') or {}
    card_url = card.get('url', '') or ''
    card_desc = card.get('description', '') or ''
    card_title = card.get('title', '') or ''
    
    combined = f"{text} {card_url} {card_desc} {card_title}"
    
    # Direct discord invites
    for match in INVITE_REGEX.findall(combined):
        invites.add(match)
        
    # Check t.co links
    tco_links = TCO_REGEX.findall(combined)
    for tco in tco_links:
        resolved = resolve_tco(tco)
        if resolved:
            m = INVITE_REGEX.search(resolved)
            if m:
                invites.add(m.group(1))
                
    return invites

def audit_discord_invite(code):
    api_url = f"https://discord.com/api/v9/invites/{code}?with_counts=true"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "msg": str(e)}
    except Exception as e:
        return {"error": "exception", "msg": str(e)}

def main():
    all_invites = {} # code -> tweet metadata
    
    for q in QUERIES:
        tweets = fetch_twitter_tweets(q, limit=15)
        print(f"    Found {len(tweets)} tweets.")
        for tw in tweets:
            invs = extract_invites_from_tweet(tw)
            for inv in invs:
                if inv not in all_invites:
                    all_invites[inv] = {
                        "code": inv,
                        "source_tweet": tw.get('url'),
                        "author": tw.get('author'),
                        "tweet_text": tw.get('text', '')[:120]
                    }
        time.sleep(1.5)

    print(f"\n==================================================")
    print(f"[+] Total unique Discord invites harvested from Twitter: {len(all_invites)}")
    print(f"==================================================\n")
    
    out_dir = r"c:\Users\paule\OneDrive\Desktop\DISCORD_BOTS\gws-bot\scratch"
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "twitter_harvested_invites.json"), "w", encoding="utf-8") as f:
        json.dump(all_invites, f, indent=2)

    # Now audit against Discord API
    audited = []
    print("[*] Auditing invites against live Discord API...\n")
    for code, meta in all_invites.items():
        data = audit_discord_invite(code)
        if "error" in data:
            print(f"[-] {code:12} -> Error {data.get('error')}")
            continue
            
        guild = data.get("guild", {})
        guild_id = guild.get("id")
        guild_name = guild.get("name")
        approx_members = data.get("approximate_member_count", 0)
        approx_presence = data.get("approximate_presence_count", 0)
        verif_level = guild.get("verification_level", 0)
        desc = guild.get("description") or ""
        
        ratio = (approx_presence / approx_members * 100) if approx_members > 0 else 0
        
        # Scoring logic
        # Disqualification:
        # > 5000 members -> CAPTCHA RISK
        # < 400 members -> too small / dead
        # verif_level == 4 -> phone gatekeep
        disqualified = False
        reasons = []
        if approx_members > 5000:
            disqualified = True
            reasons.append(f"Too large ({approx_members} > 5,000, CAPTCHA risk)")
        elif approx_members < 400:
            disqualified = True
            reasons.append(f"Too small ({approx_members} < 400)")
        if verif_level == 4:
            disqualified = True
            reasons.append("Verification Level 4 (Phone required)")
            
        score = 0
        if not disqualified:
            # Goldilocks sweetspot 800 - 3000
            if 800 <= approx_members <= 3000:
                score += 50
            else:
                score += 35
                
            # Online presence ratio
            if ratio >= 9.0:
                score += 30
            elif ratio >= 6.0:
                score += 20
            else:
                score += 10
                
            # Low verification level bonus
            if verif_level <= 1:
                score += 20
            elif verif_level <= 2:
                score += 15
                
        server_info = {
            "code": code,
            "guild_id": guild_id,
            "guild_name": guild_name,
            "members": approx_members,
            "online": approx_presence,
            "active_ratio_pct": round(ratio, 1),
            "verification_level": verif_level,
            "description": desc,
            "disqualified": disqualified,
            "reasons": reasons,
            "score": score,
            "source_tweet": meta["source_tweet"],
            "author": meta["author"]
        }
        audited.append(server_info)
        status_tag = f"SCORE: {score:2d}" if not disqualified else f"DISQUALIFIED ({', '.join(reasons)})"
        print(f"[+] {guild_name[:25]:25} | {approx_members:5d} mbrs | {approx_presence:4d} on ({ratio:4.1f}%) | Lvl {verif_level} | {status_tag}")
        time.sleep(0.5)

    with open(os.path.join(out_dir, "twitter_audited_discords.json"), "w", encoding="utf-8") as f:
        json.dump(audited, f, indent=2)

    # Sort vetted
    vetted = [s for s in audited if not s["disqualified"]]
    vetted.sort(key=lambda x: x["score"], reverse=True)
    
    print("\n" + "="*80)
    print("TOP QUALIFIED TRADING DISCORDS DISCOVERED VIA TWITTER / X:")
    print("="*80)
    for idx, s in enumerate(vetted[:10], 1):
        print(f"#{idx} {s['guild_name']} (ID: {s['guild_id']} | Code: {s['code']})")
        print(f"    Members: {s['members']} | Online: {s['online']} ({s['active_ratio_pct']}%) | Verif Level: {s['verification_level']}")
        print(f"    Score: {s['score']}/100 | Source: https://x.com/{s['author']} ({s['source_tweet']})")
        print(f"    Invite: https://discord.gg/{s['code']}\n")

if __name__ == "__main__":
    main()
