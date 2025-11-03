import os, time
from axfl.notify.discord import send_discord, GREEN, RED, YELLOW, BLUE, GRAY

def post(title, desc, color):
    send_discord(f"**{title}**", embeds=[{"title":title,"description":desc,"fields":[
        {"name":"Example Field","value":"Looks good ✅","inline":True}
    ]}], color=color)
    time.sleep(2)  # 2-second delay to avoid rate limiting

def main():
    post("SHOWCASE • TRADE WIN",  "+1.27R  ≈ +$1.27 • EUR_USD • SessionBreakout", GREEN)
    post("SHOWCASE • TRADE LOSS", "−0.80R  ≈ −$0.80 • EUR_USD • VolContraction", RED)
    post("SHOWCASE • INFO",       "ADR guard active: adr14=28.3 < min=40", YELLOW)
    post("SHOWCASE • OPEN",       "LIVE • LONG 2000u @ 1.15164  SL/TP set", BLUE)
    post("SHOWCASE • SYSTEM",     "Scheduler start, daemon heartbeat ok", GRAY)
    print("ALERTS_SHOWCASE_OK")

if __name__ == "__main__":
    main()
