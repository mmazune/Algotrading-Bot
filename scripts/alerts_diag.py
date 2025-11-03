import os
from axfl.notify.discord import send_discord, _resolve_webhook, _mask, alerts_capabilities

def main():
    url = _resolve_webhook()
    src = "env" if os.environ.get("DISCORD_WEBHOOK_URL") else ("file" if url else "none")
    code = send_discord("**ALERTS DIAG** ping", embeds=[{"title":"Diag","description":"Testing webhook post","fields":[{"name":"Source","value":src},{"name":"Capabilities","value":alerts_capabilities()}]}], color=0x3B82F6)
    print(f"ALERTS_DIAG source={src} url={_mask(url)} code={code}")

if __name__ == "__main__":
    main()
