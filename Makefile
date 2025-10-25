.PHONY: setup test run_arls run_arls_td run_arls_fh run_arls_auto run_orb_auto run_lsg_auto run_choch_auto run_breaker_auto tune_lsg compare_top live_lsg_ws live_lsg_replay live_port_replay live_port_ws live_port_london_replay live_port_london_ws scan_london scan_london_auto scan_exact replay_slice replay_slice_last replay_exact health snapshot demo_replay daily_runner risk news broker_test risk_parity digest live_oanda_ws recon digest_now live_port_profile_replay preflight service_install service_status service_logs broker_selftest alerts_test alerts_cfg clean

setup:
	python -m pip install -U pip
	pip install -r requirements.txt

test:
	pytest -q tests/

run_arls:
	python -m axfl.cli backtest --strategy arls --symbol EURUSD=X --interval 1m --days 20

run_arls_td:
	python -m axfl.cli backtest --strategy arls --symbol EURUSD --interval 1m --days 30 --source twelvedata

run_arls_fh:
	python -m axfl.cli backtest --strategy arls --symbol EURUSD --interval 1m --days 30 --source finnhub --venue OANDA

run_arls_auto:
	python -m axfl.cli backtest --strategy arls --symbol EURUSD --interval 1m --days 30 --source auto

run_orb_auto:
	python -m axfl.cli backtest --strategy orb --symbol EURUSD --interval 5m --days 30 --source auto

run_lsg_auto:
	python -m axfl.cli backtest --strategy lsg --symbol EURUSD --interval 5m --days 30 --source auto

run_choch_auto:
	python -m axfl.cli backtest --strategy choch_ob --symbol EURUSD --interval 5m --days 30 --source auto

run_breaker_auto:
	python -m axfl.cli backtest --strategy breaker --symbol EURUSD --interval 5m --days 30 --source auto

tune_lsg:
	python -m axfl.cli tune --strategy lsg --symbol EURUSD --interval 5m --days 45 --source auto --cv 4 --purge 60 --params '{"grid":{"tol_pips":[2,3],"sweep_pips":[3,4],"reentry_window_m":[20,30,45],"bos_buffer_pips":[0.5,1.0],"confirm_body_required":[true,false]}}' --spread_pips 0.6

compare_top:
	python -m axfl.cli compare --strategies lsg,orb,arls --symbol EURUSD --interval 5m --days 30 --source auto --spread_pips 0.6

live_lsg_ws:
	python -m axfl.cli live --strategy lsg --symbol EURUSD --interval 5m --source finnhub --venue OANDA --mode ws --spread_pips 0.6 --status_every 180

live_lsg_replay:
	python -m axfl.cli live --strategy lsg --symbol EURUSD --interval 5m --source auto --mode replay --spread_pips 0.6 --status_every 60

live_port_replay:
	python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay --source auto

live_port_ws:
	python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode ws --source finnhub

live_port_london_replay:
	python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay

live_port_london_ws:
	python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode ws --source finnhub

scan_london:
	python -m axfl.cli scan --symbols EURUSD,GBPUSD,XAUUSD --strategies lsg,orb,arls --days 30 --source auto --venue OANDA

scan_london_auto:
	python -m axfl.cli scan --symbols EURUSD,GBPUSD,XAUUSD --strategies lsg,orb,arls --days 45 --source auto --venue OANDA --method auto --top 3

scan_exact:
	python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb,arls --days 30 --source auto --venue OANDA --method exact --pad_before 60 --pad_after 60

replay_slice:
	@echo "Replace SCANS_JSON with your pasted JSON from scan_london output"
	python -m axfl.cli replay-slice --scans 'SCANS_JSON'

replay_slice_last:
	@echo "Replace SCANS_JSON with your pasted JSON from scan output"
	python -m axfl.cli replay-slice --scans 'SCANS_JSON' --ignore_yaml_windows true --extend 10

replay_exact:
	@echo "Replace SCANS_JSON with JSON from scan_exact output"
	python -m axfl.cli replay-slice --scans 'SCANS_JSON' --use_scan_params true --warmup_days 3 --assert_min_trades 1 --extend 0

health:
	python -m axfl.cli health --cfg axfl/config/sessions.yaml

snapshot:
	python -m axfl.cli snapshot

demo_replay:
	python -m axfl.cli demo-replay --cfg axfl/config/sessions.yaml --extend 15

daily_runner:
	python -m axfl.cli daily-runner --cfg axfl/config/sessions.yaml

risk:
	python -m axfl.cli risk --cfg axfl/config/sessions.yaml

news:
	python -m axfl.cli news --csv samples/news_events.sample.csv --hours 24

broker_test:
	python -m axfl.cli broker-test --mirror oanda --symbol EURUSD --risk_perc 0.001

risk_parity:
	python -m axfl.cli risk-parity --cfg axfl/config/sessions.yaml --lookback 20

digest:
	python -m axfl.cli digest --date $$(date +%Y%m%d)

live_oanda_ws:
	python -m axfl.cli live-oanda --cfg axfl/config/sessions.yaml --mode ws --mirror oanda

recon:
	python -m axfl.cli reconcile

digest_now:
	python -m axfl.cli digest-now

live_port_profile_replay:
	python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay --source auto --profile portfolio

preflight:
	python -m axfl.cli preflight --cfg axfl/config/sessions.yaml --profile portfolio

service_install:
	@echo "==> Installing AXFL systemd service (you may need sudo)"
	@# Ensure env dir exists and seed a sample if not present
	sudo mkdir -p /etc/axfl
	if [ ! -f /etc/axfl/axfl.env ]; then sudo cp deploy/axfl.env.sample /etc/axfl/axfl.env; fi
	sudo chown root:root /etc/axfl/axfl.env && sudo chmod 600 /etc/axfl/axfl.env
	@# Install templated unit for the current user
	sudo cp deploy/axfl-daily-runner.service /etc/systemd/system/axfl-daily-runner@.service
	sudo systemctl daemon-reload
	sudo systemctl enable axfl-daily-runner@$(USER).service
	sudo systemctl start axfl-daily-runner@$(USER).service
	@echo '###BEGIN-AXFL-OPS### {"ok":true,"service":"axfl-daily-runner@$(USER)","action":"installed_and_started"} ###END-AXFL-OPS###'

service_status:
	sudo systemctl status axfl-daily-runner@$(USER).service --no-pager

service_logs:
	journalctl -u axfl-daily-runner@$(USER).service -n 200 --no-pager

broker_selftest:
	@AXFL_SELFTEST_SL_PIPS=$${AXFL_SELFTEST_SL_PIPS:-10}; \
	AXFL_DEBUG=1 python -m axfl.cli broker-test --mirror oanda --symbol EURUSD --risk_perc 0.01 --place --sl_pips $$AXFL_SELFTEST_SL_PIPS --debug

alerts_test:
	@if [ -z "$$DISCORD_WEBHOOK_URL" ]; then \
		echo "ERROR: DISCORD_WEBHOOK_URL not set. Export it first."; \
		exit 1; \
	fi
	python scripts/send_test_alert.py --sample all

alerts_cfg:
	@echo "==> Current Alert Configuration"
	@echo "DISCORD_WEBHOOK_URL: $$(if [ -n "$$DISCORD_WEBHOOK_URL" ]; then echo '[SET]'; else echo '[NOT SET]'; fi)"
	@echo "AXFL_MIN_UNITS: $${AXFL_MIN_UNITS:-100}"
	@echo "AXFL_ALERTS_ENABLED: $${AXFL_ALERTS_ENABLED:-1}"
	@echo "AXFL_ALERT_SUMMARY_TIME_UTC: $${AXFL_ALERT_SUMMARY_TIME_UTC:-16:05}"
	@echo "AXFL_DEBUG: $${AXFL_DEBUG:-0}"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

