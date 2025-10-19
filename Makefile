.PHONY: setup test run_arls run_arls_td run_arls_fh run_arls_auto run_orb_auto run_lsg_auto run_choch_auto run_breaker_auto tune_lsg compare_top live_lsg_ws live_lsg_replay live_port_replay live_port_ws live_port_london_replay live_port_london_ws clean

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

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
