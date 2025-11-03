import os
from axfl.notify.discord import send_discord, alerts_capabilities

def main():
    code = send_discord("**ALERTS SELFTEST** This is a styled embed.", embeds=[{"title":"Self-Test","description":"Discord webhook connectivity OK.","fields":[{"name":"Capabilities","value":alerts_capabilities()}]}], color=0x3B82F6)
    print(f"ALERTS_SELFTEST code={code}")

if __name__ == "__main__":
    main()
