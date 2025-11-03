import os, sys, json, time, socket, urllib.request, urllib.error, re, pathlib

# import our resolver & sender if available; else inline minimal versions
try:
    from axfl.notify.discord import send_discord, _resolve_webhook, _mask
except Exception:
    def _resolve_webhook():
        env = (os.environ.get("DISCORD_WEBHOOK_URL") or "").strip()
        if env: return env
        fp = (os.environ.get("DISCORD_WEBHOOK_URL_FILE") or "").strip()
        cand = [fp] if fp else []
        cand.append("reports/.discord_webhook")
        for p in cand:
            if not p: continue
            try:
                txt = pathlib.Path(p).read_text().strip()
                if txt: return txt
            except Exception:
                pass
        return ""
    def _mask(u: str) -> str:
        if not u: return "EMPTY"
        if len(u) <= 16: return "***"
        return u[:8] + "…MASK…" + u[-6:]
    def _post_json(url: str, payload: dict) -> int:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.getcode()
    def send_discord(text: str, *, embeds=None, color=None) -> int:
        url = _resolve_webhook()
        if not url: return 0
        payload={"content": text[:1500]}
        if embeds:
            if color is not None:
                for e in embeds: e.setdefault("color", color)
            payload["embeds"]=embeds
        return _post_json(url, payload)

def _http_post(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            code = r.getcode()
            body = r.read().decode("utf-8", "ignore") if hasattr(r, "read") else ""
            return code, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore") if hasattr(e, "read") else ""
        return e.code, body
    except Exception as ex:
        return 0, str(ex)

def _is_valid_webhook(u: str) -> bool:
    if not u: return False
    pat = r"^https://(discord|discordapp)\.com/api/webhooks/\d+/.+"
    return re.match(pat, u) is not None

def main():
    # 0) Context
    cwd = os.getcwd()
    pyv = sys.version.split()[0]
    print(f"ALERTS_ENV cwd={cwd} py={pyv}")

    # 1) Resolve webhook
    url = _resolve_webhook()
    src = "env" if os.environ.get("DISCORD_WEBHOOK_URL") else ("file" if url else "none")
    masked = _mask(url)
    print(f"ALERTS_SOURCE src={src} url={masked}")

    # 2) Validate format
    valid = _is_valid_webhook(url)
    print(f"ALERTS_URL_VALID valid={valid}")

    # 3) Ensure fallback file contains current url (self-heal)
    try:
        pathlib.Path("reports").mkdir(exist_ok=True)
        if url:
            pathlib.Path("reports/.discord_webhook").write_text(url)
            print("ALERTS_FALLBACK_WRITE ok=1")
        else:
            print("ALERTS_FALLBACK_WRITE ok=0")
    except Exception as ex:
        print(f"ALERTS_FALLBACK_WRITE ok=0 err={ex}")

    # 4) DNS sanity (should resolve)
    try:
        ip = socket.gethostbyname("discord.com")
        print(f"ALERTS_DNS resolve=discord.com ip={ip}")
    except Exception as ex:
        print(f"ALERTS_DNS resolve=FAIL err={ex}")

    # 5) Plain content ping
    if not url:
        print("ALERTS_PING_PLAIN code=0 note=no_url")
    else:
        code1, body1 = _http_post(url, {"content": "**ALERTS PLAIN PING**"})
        print(f"ALERTS_PING_PLAIN code={code1} body_len={len(body1)}")

    # 6) Embed ping
    if url:
        code2, body2 = _http_post(url, {
            "content": "**ALERTS EMBED PING**",
            "embeds":[{"title":"Embed Ping","description":"Testing embed payload","color":0x3B82F6}]
        })
        print(f"ALERTS_PING_EMBED code={code2} body_len={len(body2)}")
    else:
        print("ALERTS_PING_EMBED code=0 note=no_url")

    # 7) Use library sender as well (should produce same result)
    try:
        c3 = send_discord("**ALERTS SEND_DISCORD()** Library path OK",
                          embeds=[{"title":"Library Call","description":"send_discord working","color":0x16A34A}])
    except Exception as ex:
        c3 = 0
    print(f"ALERTS_SEND_LIB code={c3}")

    # 8) Showcase (5 colors) to confirm visible formatting
    try:
        from axfl.notify.discord import GREEN, RED, YELLOW, BLUE, GRAY
    except Exception:
        GREEN=0x16A34A; RED=0xDC2626; YELLOW=0xF59E0B; BLUE=0x3B82F6; GRAY=0x6B7280
    if url:
        send_discord("**SHOWCASE WIN**", embeds=[{"title":"WIN","description":"+1.27R  ≈ +$1.27 • EUR_USD • SessionBreakout","color":GREEN}], color=GREEN)
        send_discord("**SHOWCASE LOSS**", embeds=[{"title":"LOSS","description":"−0.80R  ≈ −$0.80 • EUR_USD • VolContraction","color":RED}], color=RED)
        send_discord("**SHOWCASE INFO**", embeds=[{"title":"INFO","description":"ADR guard active: adr14=28.3 < min=40","color":YELLOW}], color=YELLOW)
        send_discord("**SHOWCASE OPEN**", embeds=[{"title":"OPEN","description":"LIVE • LONG 2000u @ 1.15164  SL/TP set","color":BLUE}], color=BLUE)
        send_discord("**SHOWCASE SYSTEM**", embeds=[{"title":"SYSTEM","description":"Scheduler start, heartbeat OK","color":GRAY}], color=GRAY)
        print("ALERTS_SHOWCASE_SENT ok=1")
    else:
        print("ALERTS_SHOWCASE_SENT ok=0")

if __name__ == "__main__":
    main()
