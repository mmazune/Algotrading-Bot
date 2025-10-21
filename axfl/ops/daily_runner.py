"""
Daily Runner: Automated execution of London and NY trading sessions.

Runs two sessions per weekday:
- London: 07:00-10:00 UTC
- New York: 12:30-16:00 UTC

Features:
- Finnhub WebSocket with replay failover
- Discord alerts on session start/end/errors
- Daily PnL snapshot at 16:05 UTC
- Weekend/holiday detection
"""
import os
import sys
import time
import signal
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd

from ..portfolio.engine import PortfolioEngine
from ..monitor import send_event, send_warn, send_error, send_diag, daily_snapshot
from ..portfolio.scheduler import load_sessions_yaml, normalize_schedule


class DailyRunner:
    """Orchestrates daily trading sessions with monitoring and failover."""
    
    def __init__(self, config_path: str = "axfl/config/sessions.yaml", profile: str = "portfolio"):
        """
        Initialize daily runner.
        
        Args:
            config_path: Path to sessions YAML config
            profile: YAML profile to use (default: portfolio)
        """
        self.config_path = config_path
        self.profile = profile
        self.london_engine: Optional[PortfolioEngine] = None
        self.ny_engine: Optional[PortfolioEngine] = None
        self.shutdown_requested = False
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\n[DailyRunner] Received signal {signum}, shutting down...")
        self.shutdown_requested = True
        
        # Stop engines if running
        if self.london_engine:
            self.london_engine.shutdown_requested = True
        if self.ny_engine:
            self.ny_engine.shutdown_requested = True
    
    def _is_trading_day(self) -> bool:
        """Check if today is a weekday (Mon-Fri)."""
        now = pd.Timestamp.now(tz='UTC')
        weekday = now.weekday()
        return weekday < 5  # 0=Monday, 4=Friday
    
    def _should_run_london(self) -> bool:
        """Check if London session should run now."""
        now = pd.Timestamp.now(tz='UTC')
        hour = now.hour
        minute = now.minute
        
        # London window: 07:00-10:00 UTC
        # Start slightly before for warmup
        if hour == 6 and minute >= 55:
            return True
        if hour >= 7 and hour < 10:
            return True
        
        return False
    
    def _should_run_ny(self) -> bool:
        """Check if NY session should run now."""
        now = pd.Timestamp.now(tz='UTC')
        hour = now.hour
        minute = now.minute
        
        # NY window: 12:30-16:00 UTC
        # Start slightly before for warmup
        if hour == 12 and minute >= 25:
            return True
        if hour >= 13 and hour < 16:
            return True
        
        return False
    
    def _load_session_config(self, session: str = "london") -> Dict[str, Any]:
        """
        Load and normalize session configuration.
        
        Args:
            session: "london" or "ny"
        
        Returns:
            Normalized schedule config
        """
        try:
            raw_cfg = load_sessions_yaml(self.config_path)
            
            # Use the instance profile parameter
            # If session is NY and profile doesn't exist, try portfolio_ny as fallback
            profile_to_use = self.profile
            if session == "ny" and self.profile not in raw_cfg and "portfolio_ny" in raw_cfg:
                profile_to_use = "portfolio_ny"
            
            return normalize_schedule(raw_cfg, profile=profile_to_use)
            
        except Exception as e:
            send_error(f"Failed to load {session} config", {"error": str(e)})
            raise
    
    def _run_session(self, session: str, max_retries: int = 3) -> bool:
        """
        Run a single trading session (London or NY).
        
        Args:
            session: "london" or "ny"
            max_retries: Maximum retry attempts on failure
        
        Returns:
            True if session completed successfully, False otherwise
        """
        session_label = session.upper()
        
        try:
            # Load config
            schedule_cfg = self._load_session_config(session)
            
            # Validate schedule
            if not schedule_cfg.get('symbols') or not schedule_cfg.get('strategies'):
                send_diag(f"{session_label} session: empty schedule", {
                    "reason": "empty_schedule",
                    "session": session,
                    "cfg": self.config_path
                })
                return False
            
            # Send start alert
            send_event(f"🚀 {session_label} SESSION START", {
                "session": session,
                "symbols": schedule_cfg['symbols'],
                "strategies": [s['name'] for s in schedule_cfg['strategies']],
                "source": schedule_cfg.get('source', 'finnhub'),
                "mode": "ws with replay failover"
            })
            
            # Try WebSocket first
            retry_count = 0
            mode = "ws"
            
            while retry_count < max_retries and not self.shutdown_requested:
                try:
                    print(f"\n{'='*60}")
                    print(f"  {session_label} SESSION - Attempt {retry_count + 1}/{max_retries}")
                    print(f"  Mode: {mode.upper()}")
                    print(f"{'='*60}\n")
                    
                    # Create engine
                    engine = PortfolioEngine(schedule_cfg, mode=mode, broker=None)
                    
                    if session == "london":
                        self.london_engine = engine
                    else:
                        self.ny_engine = engine
                    
                    # Run until session end or error
                    while not self.shutdown_requested:
                        now = pd.Timestamp.now(tz='UTC')
                        
                        # Check if session should end
                        if session == "london" and now.hour >= 10:
                            print(f"[DailyRunner] {session_label} session end time reached")
                            break
                        elif session == "ny" and now.hour >= 16:
                            print(f"[DailyRunner] {session_label} session end time reached")
                            break
                        
                        # Sleep briefly to avoid tight loop
                        time.sleep(5)
                    
                    # Clean shutdown
                    engine._print_status()  # Final status
                    
                    # Success
                    send_event(f"✅ {session_label} SESSION COMPLETE", {
                        "session": session,
                        "mode": mode,
                        "stats": engine._get_portfolio_stats()
                    })
                    
                    return True
                    
                except KeyboardInterrupt:
                    print(f"[DailyRunner] {session_label} session interrupted by user")
                    raise
                    
                except Exception as e:
                    retry_count += 1
                    error_msg = str(e)
                    
                    # Check if WebSocket failed, fallback to replay
                    if "websocket" in error_msg.lower() or "ws" in error_msg.lower():
                        if mode == "ws" and retry_count < max_retries:
                            send_warn(f"{session_label} WebSocket failed, falling back to replay", {
                                "error": error_msg,
                                "retry": retry_count
                            })
                            mode = "replay"
                            continue
                    
                    # Log error
                    send_error(f"{session_label} session error (attempt {retry_count})", {
                        "error": error_msg,
                        "mode": mode,
                        "traceback": traceback.format_exc()
                    })
                    
                    # Wait before retry
                    if retry_count < max_retries:
                        wait_time = min(30 * retry_count, 120)
                        print(f"[DailyRunner] Retrying in {wait_time}s...")
                        time.sleep(wait_time)
            
            # All retries failed
            send_error(f"❌ {session_label} SESSION FAILED after {max_retries} attempts", {
                "session": session
            })
            return False
            
        except Exception as e:
            send_error(f"Fatal error in {session_label} session", {
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            return False
        
        finally:
            # Cleanup
            if session == "london":
                self.london_engine = None
            else:
                self.ny_engine = None
    
    def _generate_daily_snapshot(self):
        """Generate and post daily PnL snapshot at end of day."""
        try:
            print("\n[DailyRunner] Generating daily PnL snapshot...")
            
            result = daily_snapshot(trades_dir="data/trades", out_dir="reports")
            
            # Send alert with summary
            send_event("📊 DAILY PNL SNAPSHOT", {
                "date": result['date'],
                "total_r": result['totals']['r'],
                "total_pnl": result['totals']['pnl'],
                "total_trades": result['totals']['trades'],
                "by_strategy": result['by_strategy'],
                "csv": result.get('csv', ''),
                "md": result.get('md', '')
            })
            
            print(f"[DailyRunner] Snapshot saved: {result.get('csv', '')}")
            
        except Exception as e:
            send_error("Failed to generate daily snapshot", {
                "error": str(e),
                "traceback": traceback.format_exc()
            })
    
    def run(self):
        """
        Main entry point: run daily trading sessions.
        
        Flow:
        1. Check if trading day (Mon-Fri)
        2. Wait for London session time (07:00 UTC)
        3. Run London session (07:00-10:00)
        4. Wait for NY session time (12:30 UTC)
        5. Run NY session (12:30-16:00)
        6. Generate daily PnL snapshot (16:05 UTC)
        7. Sleep until next day
        """
        print("="*60)
        print("  AXFL DAILY RUNNER")
        print("="*60)
        print(f"  Config: {self.config_path}")
        print(f"  Sessions: London (07:00-10:00 UTC), NY (12:30-16:00 UTC)")
        print(f"  Mode: Finnhub WS with replay failover")
        print("="*60 + "\n")
        
        while not self.shutdown_requested:
            try:
                now = pd.Timestamp.now(tz='UTC')
                
                # Check if trading day
                if not self._is_trading_day():
                    print(f"[DailyRunner] {now.strftime('%A')} - Weekend/Holiday, sleeping...")
                    time.sleep(3600)  # Check hourly
                    continue
                
                # London session
                if self._should_run_london():
                    # Wait until exactly 07:00
                    while now.hour < 7 and not self.shutdown_requested:
                        time.sleep(30)
                        now = pd.Timestamp.now(tz='UTC')
                    
                    if not self.shutdown_requested:
                        self._run_session("london")
                
                # NY session
                if self._should_run_ny():
                    # Wait until exactly 12:30
                    while (now.hour < 12 or (now.hour == 12 and now.minute < 30)) and not self.shutdown_requested:
                        time.sleep(30)
                        now = pd.Timestamp.now(tz='UTC')
                    
                    if not self.shutdown_requested:
                        self._run_session("ny")
                
                # Daily snapshot at 16:05 UTC
                now = pd.Timestamp.now(tz='UTC')
                if now.hour == 16 and now.minute >= 5:
                    self._generate_daily_snapshot()
                    
                    # Sleep until next day (restart at 06:00 UTC)
                    tomorrow = now + timedelta(days=1)
                    wakeup_time = tomorrow.replace(hour=6, minute=0, second=0, microsecond=0)
                    sleep_seconds = (wakeup_time - now).total_seconds()
                    
                    print(f"\n[DailyRunner] Trading complete for {now.date()}")
                    print(f"[DailyRunner] Sleeping until {wakeup_time.strftime('%Y-%m-%d %H:%M UTC')}")
                    
                    time.sleep(sleep_seconds)
                else:
                    # Check again in 5 minutes
                    time.sleep(300)
                    
            except KeyboardInterrupt:
                print("\n[DailyRunner] Shutdown requested by user")
                break
                
            except Exception as e:
                send_error("DailyRunner error", {
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
                # Wait before retry
                time.sleep(300)
        
        print("[DailyRunner] Shutdown complete")


def run_daily_sessions(config_path: str = "axfl/config/sessions.yaml", profile: str = "portfolio"):
    """
    Convenience function to run daily sessions.
    
    Args:
        config_path: Path to sessions YAML config
        profile: YAML profile to use (default: portfolio)
    """
    runner = DailyRunner(config_path=config_path, profile=profile)
    runner.run()
