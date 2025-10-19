#!/usr/bin/env python3
"""
🔄 WALK-FORWARD ANALYSIS WITH OPTIMIZATION
==========================================

This script implements a complete walk-forward analysis framework with in-sample
optimization and out-of-sample testing for algorithmic trading strategies.

Walk-forward analysis with optimization provides:
1. Rolling window data splitting for robust validation
2. In-sample parameter optimization for each window
3. Out-of-sample testing with optimized parameters
4. Collection of performance results across multiple periods
5. Prevention of overfitting and look-ahead bias

Key Features:
- SMA crossover strategy implementation
- Grid search parameter optimization
- Equity curve calculation and tracking
- Professional logging and validation
- Extensible framework for strategy integration

Strategy Logic:
- Buy signal: Short MA crosses above Long MA
- Sell signal: Short MA crosses below Long MA
- Position sizing: Full allocation (100% of capital)
- Commission: 0.1% per trade (realistic trading costs)

Key Improvements in v2.0.1:
- Accurate win rate calculation based on completed trades
- Refined optimization logic with proper initial capital handling
- Centralized imports for better code organization
- Enhanced backtesting logic with precise trade closing

Author: Walk-Forward Optimization Framework
Date: September 2025
Version: 2.0.1
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Generator, Tuple, Optional, Dict, List
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

def validate_parameters(data: pd.DataFrame, in_sample_size: int, 
                        out_of_sample_size: int, step_size: int) -> None:
    """
    Validate input parameters for walk-forward analysis
    
    Performs comprehensive validation of input parameters to ensure
    the walk-forward analysis can proceed without errors.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Historical price data with DatetimeIndex
    in_sample_size : int
        Number of days for in-sample (training) period
    out_of_sample_size : int
        Number of days for out-of-sample (testing) period
    step_size : int
        Number of days to advance between windows
        
    Raises:
    -------
    ValueError
        If any parameter validation fails
    TypeError
        If data types are incorrect
    """
    # Data validation
    if not isinstance(data, pd.DataFrame):
        raise TypeError("Data must be a pandas DataFrame")
    
    if data.empty:
        raise ValueError("Data DataFrame cannot be empty")
    
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("Data must have a DatetimeIndex")
    
    # Check for required columns
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing_columns = [col for col in required_columns if col not in data.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")
    
    # Parameter validation
    if not all(isinstance(x, int) for x in [in_sample_size, out_of_sample_size, step_size]):
        raise TypeError("Window sizes and step size must be integers")
    
    if in_sample_size <= 0:
        raise ValueError("In-sample size must be positive")
    
    if out_of_sample_size <= 0:
        raise ValueError("Out-of-sample size must be positive")
    
    if step_size <= 0:
        raise ValueError("Step size must be positive")
    
    # Minimum data requirement
    min_required_days = in_sample_size + out_of_sample_size
    if len(data) < min_required_days:
        raise ValueError(f"Insufficient data: {len(data)} days available, "
                         f"{min_required_days} days required")
    
    print("✅ Parameter validation passed")

def backtest_strategy(data: pd.DataFrame, short_ma_period: int, 
                      long_ma_period: int, initial_capital: float = 100000.0,
                      commission: float = 0.001) -> Dict:
    """
    Backtest SMA crossover strategy on provided data slice
    
    Implements a simple moving average crossover strategy with realistic
    trading costs and position management. This improved version provides
    accurate win rate calculation based on completed trades.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Historical price data with OHLCV columns
    short_ma_period : int
        Period for short moving average (e.g., 10, 20, 50)
    long_ma_period : int
        Period for long moving average (e.g., 50, 100, 200)
    initial_capital : float, default=100000.0
        Starting capital for backtesting
    commission : float, default=0.001
        Commission rate per trade (0.1% = 0.001)
        
    Returns:
    --------
    Dict
        Backtest results containing:
        - final_equity: Final portfolio value
        - equity_curve: Series of daily equity values
        - total_return: Total return percentage
        - num_trades: Number of completed trades executed
        - win_rate: Percentage of profitable trades
    """
    # Validate inputs
    if short_ma_period >= long_ma_period or len(data) < long_ma_period:
        return {
            'final_equity': initial_capital,
            'equity_curve': pd.Series([initial_capital] * len(data), index=data.index),
            'total_return': 0.0,
            'num_trades': 0,
            'win_rate': 0.0
        }
    
    # Calculate moving averages
    data = data.copy()
    data['short_ma'] = data['Close'].rolling(window=short_ma_period).mean()
    data['long_ma'] = data['Close'].rolling(window=long_ma_period).mean()
    
    # Generate signals
    data['signal'] = 0
    data.loc[data['short_ma'] > data['long_ma'], 'signal'] = 1  # Buy signal
    data.loc[data['short_ma'] <= data['long_ma'], 'signal'] = -1  # Sell signal
    
    # Calculate signal changes (trade triggers)
    data['position'] = data['signal'].diff().fillna(0)
    
    # Initialize tracking variables
    current_cash = initial_capital
    current_shares = 0
    equity_curve = []
    trades = []  # Track completed trade P&L
    trade_open_price = 0
    current_position = 0  # 0 = no position, 1 = long, -1 = short
    
    # Execute strategy
    for i, (date, row) in enumerate(data.iterrows()):
        # Skip if we don't have enough data for moving averages
        if pd.isna(row['short_ma']) or pd.isna(row['long_ma']):
            equity_curve.append(initial_capital)
            continue
        
        current_price = row['Close']
        signal = row['signal']
        prev_position = current_position
        
        # Check for position changes
        if signal != prev_position:
            # Close existing position if any
            if prev_position != 0:
                trade_pnl = 0
                if prev_position == 1:  # Closing a long position
                    exit_price = current_price * (1 - commission)
                    trade_pnl = current_shares * (exit_price - trade_open_price)
                elif prev_position == -1:  # Closing a short position
                    exit_price = current_price * (1 + commission)
                    trade_pnl = current_shares * (trade_open_price - exit_price)
                
                trades.append(trade_pnl)
                current_cash += (current_shares * trade_open_price) + trade_pnl
                current_shares = 0
            
            # Open new position
            if signal == 1:  # Open long position
                trade_open_price = current_price * (1 + commission)
                current_shares = current_cash / trade_open_price
                current_cash = 0
                current_position = 1
            elif signal == -1:  # Open short position
                trade_open_price = current_price * (1 - commission)
                current_shares = current_cash / trade_open_price
                current_cash = 0
                current_position = -1
            else:  # No position
                current_position = 0
        
        # Calculate current equity
        if current_position == 1:  # Long position
            current_equity = current_shares * current_price
        elif current_position == -1:  # Short position
            current_equity = current_cash + current_shares * (2 * trade_open_price - current_price)
        else:  # No position
            current_equity = current_cash
        
        equity_curve.append(current_equity)
    
    # Close any remaining position at the end
    if current_position != 0:
        final_price = data['Close'].iloc[-1]
        trade_pnl = 0
        if current_position == 1:  # Closing a long position
            exit_price = final_price * (1 - commission)
            trade_pnl = current_shares * (exit_price - trade_open_price)
        elif current_position == -1:  # Closing a short position
            exit_price = final_price * (1 + commission)
            trade_pnl = current_shares * (trade_open_price - exit_price)
        
        trades.append(trade_pnl)
        final_equity = initial_capital + sum(trades)
    else:
        final_equity = initial_capital + sum(trades)

    # Calculate performance metrics
    equity_series = pd.Series(equity_curve, index=data.index)
    total_return = ((final_equity - initial_capital) / initial_capital) * 100
    num_trades = len(trades)
    
    # Calculate accurate win rate based on profitable trades
    win_rate = (sum(1 for pnl in trades if pnl > 0) / num_trades) * 100 if num_trades > 0 else 0.0
    
    return {
        'final_equity': final_equity,
        'equity_curve': equity_series,
        'total_return': total_return,
        'num_trades': num_trades,
        'win_rate': win_rate
    }

def optimize_parameters(data: pd.DataFrame, short_ma_range: range, 
                        long_ma_range: range, initial_capital: float = 100000.0) -> Dict:
    """
    Optimize SMA crossover strategy parameters using grid search
    
    Performs exhaustive grid search optimization over specified parameter ranges
    to find the combination that maximizes final equity. This improved version
    uses initial capital as the baseline for comparison.
    
    Parameters:
    -----------
    data : pd.DataFrame
        In-sample data for parameter optimization
    short_ma_range : range
        Range of short moving average periods to test
    long_ma_range : range
        Range of long moving average periods to test
    initial_capital : float, default=100000.0
        Starting capital for optimization
        
    Returns:
    --------
    Dict
        Optimization results containing:
        - best_short_ma: Optimal short MA period
        - best_long_ma: Optimal long MA period
        - best_equity: Best final equity achieved
        - best_return: Best total return percentage
        - combinations_tested: Number of parameter combinations tested
        - optimization_summary: Summary statistics
    """
    print(f"    🔍 Optimizing parameters...")
    print(f"      📊 Short MA range: {list(short_ma_range)}")
    print(f"      📊 Long MA range: {list(long_ma_range)}")
    
    best_equity = initial_capital  # Initialize with starting capital to handle losses
    best_params = None
    combinations_tested = 0
    all_results = []
    
    # Grid search over all parameter combinations
    for short_ma in short_ma_range:
        for long_ma in long_ma_range:
            # Skip invalid combinations
            if short_ma >= long_ma:
                continue
            
            combinations_tested += 1
            
            # Backtest current parameter combination
            results = backtest_strategy(
                data=data,
                short_ma_period=short_ma,
                long_ma_period=long_ma,
                initial_capital=initial_capital
            )
            
            # Track results
            all_results.append({
                'short_ma': short_ma,
                'long_ma': long_ma,
                'final_equity': results['final_equity'],
                'total_return': results['total_return'],
                'num_trades': results['num_trades']
            })
            
            # Update best parameters if this combination is better
            if results['final_equity'] > best_equity:
                best_equity = results['final_equity']
                best_params = (short_ma, long_ma)
    
    # Calculate optimization summary statistics
    if all_results:
        returns = [r['total_return'] for r in all_results]
        trades = [r['num_trades'] for r in all_results]
        
        optimization_summary = {
            'mean_return': np.mean(returns),
            'std_return': np.std(returns),
            'max_return': np.max(returns),
            'min_return': np.min(returns),
            'mean_trades': np.mean(trades),
            'max_trades': np.max(trades)
        }
    else:
        optimization_summary = {}
    
    # Handle case where no valid combinations were found
    if best_params is None:
        print(f"      ⚠️ No valid parameter combinations found")
        return {
            'best_short_ma': short_ma_range[0],
            'best_long_ma': long_ma_range[-1],
            'best_equity': initial_capital,
            'best_return': 0.0,
            'combinations_tested': 0,
            'optimization_summary': {}
        }
    
    best_results = backtest_strategy(data, best_params[0], best_params[1], initial_capital)
    
    print(f"      ✅ Tested {combinations_tested} combinations")
    print(f"      🎯 Best parameters: SMA({best_params[0]}, {best_params[1]})")
    print(f"      💰 Best equity: ${best_equity:,.2f}")
    print(f"      📈 Best return: {best_results['total_return']:.2f}%")
    
    return {
        'best_short_ma': best_params[0],
        'best_long_ma': best_params[1],
        'best_equity': best_equity,
        'best_return': best_results['total_return'],
        'best_num_trades': best_results['num_trades'],
        'combinations_tested': combinations_tested,
        'optimization_summary': optimization_summary,
        'best_results': best_results
    }

def create_windows(data: pd.DataFrame, in_sample_size: int, 
                    out_of_sample_size: int, step_size: int = None
                    ) -> Generator[Tuple[datetime, datetime, datetime, datetime], None, None]:
    """
    Generate rolling windows for walk-forward analysis
    
    This function creates a series of rolling windows that split historical data
    into in-sample (training) and out-of-sample (testing) periods.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Historical price data with DatetimeIndex
    in_sample_size : int
        Number of trading days for in-sample (training) period
    out_of_sample_size : int
        Number of trading days for out-of-sample (testing) period
    step_size : int, optional
        Number of days to advance between windows
        
    Yields:
    -------
    Generator[Tuple[datetime, datetime, datetime, datetime], None, None]
        Tuple containing (in_sample_start, in_sample_end, 
                          out_of_sample_start, out_of_sample_end)
    """
    # Default step size to out_of_sample_size for non-overlapping windows
    if step_size is None:
        step_size = out_of_sample_size
        print(f"📊 Using non-overlapping windows (step_size = {step_size})")

    # Validate input parameters
    validate_parameters(data, in_sample_size, out_of_sample_size, step_size)
    
    # Calculate total window size and validate data sufficiency
    total_window_size = in_sample_size + out_of_sample_size
    data_length = len(data)
    
    print(f"📈 Data Summary:")
    print(f"    📅 Total data points: {data_length}")
    print(f"    📅 Data range: {data.index[0].strftime('%Y-%m-%d')} to {data.index[-1].strftime('%Y-%m-%d')}")
    print(f"    🏋️ In-sample size: {in_sample_size} days")
    print(f"    🧪 Out-of-sample size: {out_of_sample_size} days")
    print(f"    🔄 Step size: {step_size} days")
    
    window_count = 0
    current_start_idx = 0
    
    while True:
        # Calculate window boundaries
        in_sample_start_idx = current_start_idx
        in_sample_end_idx = in_sample_start_idx + in_sample_size - 1
        out_of_sample_start_idx = in_sample_end_idx + 1
        out_of_sample_end_idx = out_of_sample_start_idx + out_of_sample_size - 1
        
        # Check if we have sufficient data for complete window
        if out_of_sample_end_idx >= data_length:
            print(f"📋 Window generation complete: {window_count} windows created")
            break
        
        # Extract dates from data index
        in_sample_start = data.index[in_sample_start_idx]
        in_sample_end = data.index[in_sample_end_idx]
        out_of_sample_start = data.index[out_of_sample_start_idx]
        out_of_sample_end = data.index[out_of_sample_end_idx]
        
        window_count += 1
        
        # Yield the window boundaries
        yield (in_sample_start, in_sample_end, out_of_sample_start, out_of_sample_end)
        
        # Advance to next window
        current_start_idx += step_size

def generate_sample_data(start_date: str = "2015-01-01", 
                        end_date: str = "2024-12-31",
                        symbol: str = "SAMPLE") -> pd.DataFrame:
    """
    Generate sample financial data for framework testing
    
    Creates realistic sample data that mimics typical financial time series
    characteristics for testing the walk-forward framework.
    
    Parameters:
    -----------
    start_date : str
        Start date in YYYY-MM-DD format
    end_date : str
        End date in YYYY-MM-DD format
    symbol : str
        Symbol identifier for the sample data
        
    Returns:
    --------
    pd.DataFrame
        Sample financial data with OHLCV columns and DatetimeIndex
    """
    print(f"📊 Generating sample data for {symbol}...")
    
    # Create date range (business days only)
    date_range = pd.bdate_range(start=start_date, end=end_date, freq='B')
    
    # Generate realistic price data using random walk with drift
    np.random.seed(42)  # For reproducible results
    n_days = len(date_range)
    
    # Price parameters
    initial_price = 100.0
    annual_drift = 0.08  # 8% annual expected return
    annual_volatility = 0.25  # 25% annual volatility
    
    # Convert to daily parameters
    daily_drift = annual_drift / 252
    daily_volatility = annual_volatility / np.sqrt(252)
    
    # Generate price returns
    returns = np.random.normal(daily_drift, daily_volatility, n_days)
    
    # Calculate cumulative prices
    price_series = initial_price * np.exp(np.cumsum(returns))
    
    # Generate OHLCV data
    data = pd.DataFrame(index=date_range)
    data['Close'] = price_series
    
    # Generate High, Low, Open with realistic relationships
    daily_range = np.random.uniform(0.005, 0.03, n_days)  # 0.5% to 3% daily range
    data['High'] = data['Close'] * (1 + daily_range * np.random.uniform(0.3, 1.0, n_days))
    data['Low'] = data['Close'] * (1 - daily_range * np.random.uniform(0.3, 1.0, n_days))
    data['Open'] = data['Low'] + (data['High'] - data['Low']) * np.random.uniform(0.2, 0.8, n_days)
    
    # Generate volume data
    base_volume = 1000000
    volume_variance = np.random.uniform(0.5, 2.0, n_days)
    data['Volume'] = (base_volume * volume_variance).astype(int)
    
    # Ensure High >= Low and price relationships
    data['High'] = np.maximum(data['High'], data[['Open', 'Close']].max(axis=1))
    data['Low'] = np.minimum(data['Low'], data[['Open', 'Close']].min(axis=1))
    
    print(f"✅ Generated {len(data)} days of sample data")
    print(f"📈 Data range: {data.index[0].strftime('%Y-%m-%d')} to {data.index[-1].strftime('%Y-%m-%d')}")
    print(f"📊 Price range: ${data['Close'].min():.2f} to ${data['Close'].max():.2f}")
    
    return data

def main():
    """
    Main execution function for walk-forward optimization framework
    
    This function demonstrates the complete walk-forward analysis with optimization:
    1. Sample data generation for testing
    2. Window parameter configuration
    3. Rolling window generation with optimization
    4. In-sample parameter optimization for each window
    5. Out-of-sample testing with optimized parameters
    6. Collection of results for analysis
    """
    print("🔄 WALK-FORWARD ANALYSIS WITH OPTIMIZATION")
    print("=" * 55)
    print(f"📅 Framework Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🎯 Purpose: Complete walk-forward optimization with SMA crossover strategy")
    
    # 1. GENERATE SAMPLE DATA
    print(f"\n📊 STEP 1: DATA PREPARATION")
    print("-" * 30)
    
    try:
        # Generate sample financial data for testing
        data = generate_sample_data(
            start_date="2015-01-01",
            end_date="2024-12-31",
            symbol="TEST_ASSET"
        )
        
        print(f"📈 Sample data statistics:")
        print(f"    📊 Total observations: {len(data)}")
        print(f"    📅 First date: {data.index[0].strftime('%Y-%m-%d')}")
        print(f"    📅 Last date: {data.index[-1].strftime('%Y-%m-%d')}")
        print(f"    💰 Price statistics: ${data['Close'].min():.2f} - ${data['Close'].max():.2f}")
        
    except Exception as e:
        print(f"❌ Data generation failed: {str(e)}")
        return
    
    # 2. CONFIGURE OPTIMIZATION PARAMETERS
    print(f"\n🔧 STEP 2: OPTIMIZATION CONFIGURATION")
    print("-" * 40)
    
    # Walk-forward parameters
    in_sample_size = 504    # ~2 years of business days (252 * 2)
    out_of_sample_size = 126  # ~6 months of business days
    step_size = 126         # Non-overlapping windows
    
    # Strategy optimization ranges
    short_ma_range = range(5, 51, 5)   # 5, 10, 15, 20, 25, 30, 35, 40, 45, 50
    long_ma_range = range(20, 201, 10) # 20, 30, 40, ..., 190, 200
    initial_capital = 100000.0
    
    print(f"📋 Walk-Forward Configuration:")
    print(f"    🏋️ In-Sample Period: {in_sample_size} days (~{in_sample_size/252:.1f} years)")
    print(f"    🧪 Out-of-Sample Period: {out_of_sample_size} days (~{out_of_sample_size/252:.1f} months)")
    print(f"    🔄 Step Size: {step_size} days (non-overlapping)")
    
    print(f"📊 Optimization Configuration:")
    print(f"    📈 Short MA range: {list(short_ma_range)}")
    print(f"    📈 Long MA range: {list(long_ma_range)}")
    print(f"    💰 Initial capital: ${initial_capital:,.0f}")
    
    # Calculate expected combinations
    valid_combinations = sum(1 for s in short_ma_range for l in long_ma_range if s < l)
    print(f"    🔍 Parameter combinations to test: {valid_combinations}")
    
    # 3. EXECUTE WALK-FORWARD OPTIMIZATION
    print(f"\n🔄 STEP 3: WALK-FORWARD OPTIMIZATION EXECUTION")
    print("-" * 50)
    
    try:
        # Generate rolling windows
        windows = list(create_windows(
            data=data,
            in_sample_size=in_sample_size,
            out_of_sample_size=out_of_sample_size,
            step_size=step_size
        ))
        
        if not windows:
            print("⚠️ No windows generated - insufficient data")
            return
        
        print(f"✅ Generated {len(windows)} rolling windows for optimization")
        
        # Initialize results collection
        out_of_sample_equity_curves = []
        window_summaries = []
        
        # Process each window
        for window_idx, (in_start, in_end, out_start, out_end) in enumerate(windows, 1):
            print(f"\n📊 WINDOW {window_idx}/{len(windows)}")
            print("-" * 30)
            print(f"🏋️ In-Sample:  {in_start.strftime('%Y-%m-%d')} to {in_end.strftime('%Y-%m-%d')}")
            print(f"🧪 Out-Sample: {out_start.strftime('%Y-%m-%d')} to {out_end.strftime('%Y-%m-%d')}")
            
            # Extract data slices
            in_sample_data = data.loc[in_start:in_end].copy()
            out_sample_data = data.loc[out_start:out_end].copy()
            
            print(f"    📊 In-sample data: {len(in_sample_data)} days")
            print(f"    📊 Out-sample data: {len(out_sample_data)} days")
            
            # STEP 3A: IN-SAMPLE OPTIMIZATION
            print(f"\n    🔍 IN-SAMPLE OPTIMIZATION")
            optimization_start_time = datetime.now()
            
            optimization_result = optimize_parameters(
                data=in_sample_data,
                short_ma_range=short_ma_range,
                long_ma_range=long_ma_range,
                initial_capital=initial_capital
            )
            
            optimization_time = (datetime.now() - optimization_start_time).total_seconds()
            print(f"      ⏱️ Optimization completed in {optimization_time:.1f} seconds")
            
            # STEP 3B: OUT-OF-SAMPLE TESTING
            print(f"\n    🧪 OUT-OF-SAMPLE TESTING")
            best_short_ma = optimization_result['best_short_ma']
            best_long_ma = optimization_result['best_long_ma']
            
            print(f"      🎯 Testing parameters: SMA({best_short_ma}, {best_long_ma})")
            
            # Backtest on out-of-sample data
            out_sample_result = backtest_strategy(
                data=out_sample_data,
                short_ma_period=best_short_ma,
                long_ma_period=best_long_ma,
                initial_capital=initial_capital
            )
            
            print(f"      💰 Out-sample final equity: ${out_sample_result['final_equity']:,.2f}")
            print(f"      📈 Out-sample return: {out_sample_result['total_return']:.2f}%")
            print(f"      🔄 Out-sample trades: {out_sample_result['num_trades']}")
            print(f"      🎯 Out-sample win rate: {out_sample_result['win_rate']:.1f}%")
            
            # STEP 3C: COLLECT RESULTS
            window_summary = {
                'window': window_idx,
                'in_sample_start': in_start,
                'in_sample_end': in_end,
                'out_sample_start': out_start,
                'out_sample_end': out_end,
                'best_short_ma': best_short_ma,
                'best_long_ma': best_long_ma,
                'in_sample_return': optimization_result['best_return'],
                'out_sample_return': out_sample_result['total_return'],
                'out_sample_equity': out_sample_result['final_equity'],
                'out_sample_trades': out_sample_result['num_trades'],
                'combinations_tested': optimization_result['combinations_tested'],
                'optimization_time': optimization_time
            }
            
            window_summaries.append(window_summary)
            out_of_sample_equity_curves.append(out_sample_result['equity_curve'])
            
            print(f"    ✅ Window {window_idx} processing complete")
        
        # 4. SUMMARY RESULTS
        print(f"\n📊 STEP 4: WALK-FORWARD OPTIMIZATION SUMMARY")
        print("=" * 50)
        
        print(f"🎯 Overall Results:")
        print(f"    🔄 Windows processed: {len(window_summaries)}")
        print(f"    📈 Total parameter combinations tested: {sum(w['combinations_tested'] for w in window_summaries):,}")
        print(f"    ⏱️ Total optimization time: {sum(w['optimization_time'] for w in window_summaries):.1f} seconds")
        
        print(f"\n📋 Window-by-Window Results:")
        print("-" * 60)
        
        for summary in window_summaries:
            print(f"🔄 Window {summary['window']}:")
            print(f"    🎯 Best Parameters: SMA({summary['best_short_ma']}, {summary['best_long_ma']})")
            print(f"    🏋️ In-Sample Return: {summary['in_sample_return']:.2f}%")
            print(f"    🧪 Out-Sample Return: {summary['out_sample_return']:.2f}%")
            print(f"    💰 Out-Sample Equity: ${summary['out_sample_equity']:,.2f}")
            print(f"    🔄 Out-Sample Trades: {summary['out_sample_trades']}")
            print(f"    🔍 Combinations Tested: {summary['combinations_tested']}")
            print()
            
        # Calculate aggregate statistics
        out_sample_returns = [s['out_sample_return'] for s in window_summaries]
        out_sample_trades = [s['out_sample_trades'] for s in window_summaries]
        
        print(f"📈 Aggregate Statistics:")
        print(f"    📊 Average out-sample return: {np.mean(out_sample_returns):.2f}%")
        print(f"    📊 Std dev out-sample return: {np.std(out_sample_returns):.2f}%")
        print(f"    📊 Best out-sample return: {np.max(out_sample_returns):.2f}%")
        print(f"    📊 Worst out-sample return: {np.min(out_sample_returns):.2f}%")
        print(f"    🔄 Average trades per window: {np.mean(out_sample_trades):.1f}")
        print(f"    🔄 Total out-sample trades: {sum(out_sample_trades)}")
        
        # Most common parameter combinations
        param_combinations = [(s['best_short_ma'], s['best_long_ma']) for s in window_summaries]
        param_counts = Counter(param_combinations)
        most_common = param_counts.most_common(3)
        
        print(f"\n🎯 Most Common Parameter Combinations:")
        for i, ((short_ma, long_ma), count) in enumerate(most_common, 1):
            print(f"    {i}. SMA({short_ma}, {long_ma}): {count} windows ({count/len(window_summaries)*100:.1f}%)")
        
        print(f"\n✅ WALK-FORWARD OPTIMIZATION COMPLETE!")
        print("=" * 60)
        print(f"📊 Collected {len(out_of_sample_equity_curves)} out-of-sample equity curves")
        print(f"🎯 Framework ready for results aggregation and final analysis")
        
    except Exception as e:
        print(f"❌ Walk-forward optimization failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
