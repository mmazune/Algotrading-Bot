# 🚀 Hybrid Algorithmic Trading System with RSI Confirmation

A comprehensive algorithmic trading backtesting system featuring hybrid SMA crossover strategy with RSI confirmation filter, delivering exceptional performance with 450.10% cumulative returns.

## 📁 Project Structure

```
Algotrading-Bot/
├── � algorithmic_trading_system.py    # Main hybrid trading strategy (450.10% returns)
├── �📊 Financial_Data_Analysis.ipynb    # Financial data exploration notebook
├── 🤖 automated_data_pipeline_with_rotation.py  # Enhanced data pipeline
├── 📋 requirements.txt                 # Python dependencies
├── 🔄 .github/workflows/               # GitHub Actions automation
│   └── data-pipeline.yml              # Automated data collection workflow
├── 📚 docs/                           # Documentation
│   ├── API_KEY_ROTATION_GUIDE.md      # Multi-key setup guide
│   ├── GITHUB_SECRETS_SETUP.md        # GitHub Actions configuration
│   └── PIPELINE_IMPLEMENTATION_SUMMARY.md # Complete implementation guide
├── 🔧 scripts/                        # Core utilities
│   ├── api_rotation.py                # API key rotation logic
│   ├── config.py                      # Configuration settings
│   ├── data_transformer.py            # Data processing utilities
│   ├── finnhub_integration.py         # Finnhub API integration
│   └── main_data_collector.py         # Main data collection script
├── 🌐 apis/                          # API modules
│   ├── __init__.py                    # Package initialization
│   └── twelve_data.py                 # TwelveData API integration
└── 📊 plots/                         # Generated performance charts
```

## 🎯 Key Features

### 🏆 **Hybrid Trading Strategy (BREAKTHROUGH PERFORMANCE)**
- **450.10% Cumulative Return**: Exceptional performance vs 69.07% original SMA strategy
- **RSI Confirmation Filter**: Smart momentum filter with relaxed thresholds (30/70)
- **4-Parameter Optimization**: SMA(n1,n2) + RSI(lower,upper) with walk-forward validation
- **1.072 Average Sharpe Ratio**: Excellent risk-adjusted returns across all periods

### 🔄 **Automated Data Pipeline**
- **Multi-Source Collection**: Finnhub + TwelveData APIs for redundancy
- **API Key Rotation**: Intelligent rotation across 7+ keys per service
- **7x Rate Limit Capacity**: Enhanced throughput for data collection
- **GitHub Actions Integration**: Fully automated daily data updates

### 📈 **Performance Analytics & Validation**
- **Walk-Forward Optimization**: 6-period validation with 3-year training windows
- **Risk-Adjusted Metrics**: Sharpe ratio optimization and drawdown analysis
- **Professional Visualization**: Comprehensive performance charts and reports
- **Statistical Validation**: Robust out-of-sample testing and parameter optimization

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Hybrid Trading System
```bash
python algorithmic_trading_system.py
```

### 3. Expected Output
```
🚀 HYBRID ALGORITHMIC TRADING SYSTEM WITH RSI CONFIRMATION
📊 STRATEGY PERFORMANCE COMPARISON:
   🥇 Hybrid RSI Strategy:       450.10% cumulative return
   🥉 Original SMA Strategy:     69.07% cumulative return
   🥈 Previous RSI Strategy:      3.01% cumulative return
```

## 📊 Strategy Performance

### **🏆 Hybrid Strategy Results**
- **Cumulative Return**: 450.10% (vs 69.07% original SMA)
- **Performance Improvement**: +381.03% over baseline
- **Average Sharpe Ratio**: 1.072 (excellent risk-adjusted returns)
- **Trade Frequency**: 3.2 trades per period (optimal frequency)
- **Win Rate**: 41.94% average with smart risk management

### **🧠 Strategy Logic**
- **Buy Signal**: Short SMA crosses above Long SMA AND RSI < 70 (not overbought)
- **Sell Signal**: Short SMA crosses below Long SMA AND RSI > 30 (not oversold)
- **Parameter Optimization**: 4-parameter grid search (n1, n2, rsi_lower, rsi_upper)
- **Validation Method**: Walk-forward optimization with 6 non-overlapping periods

## 📋 Alternative Analysis Tools

### **Financial Data Analysis Notebook**
For exploratory analysis and visualization:
```bash
jupyter lab Financial_Data_Analysis.ipynb
```

### **Section 1: Setup & Configuration (Cells 1-2)**
- Library imports and environment setup
- MinIO cloud storage configuration
- Trading parameters initialization

### **Section 2: Data Loading & Preparation (Cells 3-7)**
- Multi-source data fetching (Finnhub, TwelveData)
- Data cleaning and preprocessing
- Historical data analysis and visualization

### **Section 3: Technical Indicators Analysis (Cells 8-13)**
- Moving averages (SMA 20/50)
- RSI momentum indicator
- MACD trend analysis
- Bollinger Bands volatility
- Visual indicator analysis

### **Section 4: Signal Generation & Analysis (Cells 14-18)**
- Individual signal generation
- Enhanced weighted scoring system
- Signal strength distribution analysis
- Combined signal visualization

### **Section 5: Backtesting & Strategy Optimization (Cells 19-26)**
- Enhanced backtesting with thresholds
- Parameter optimization
- Trade simulation and analysis
- Performance metrics calculation

### **Section 6: Walk-Forward Optimization (Cells 27-29)**
- Multi-period strategy validation
- Rolling window optimization
- Out-of-sample performance testing
- Robustness analysis

### **Section 7: Performance Visualization (Cells 30-31)**
- Cumulative returns analysis
- Daily return distribution
- Drawdown analysis and risk metrics

## 🎯 Strategy Performance

### **Enhanced Results vs Original:**
- **Total Return**: +2.61% vs -1.48% (original)
- **Total Trades**: 80 vs 6 (original)
- **Win Rate**: Improved across all periods
- **Max Drawdown**: Controlled at -1.48%
- **Signal Generation**: 102 trades vs 0 (original AND logic)

### **Key Improvements:**
- ✅ **Weighted Scoring**: Flexible signal strength analysis
- ✅ **Threshold Optimization**: Configurable conviction levels  
- ✅ **Multi-Period Validation**: Consistent performance across time
- ✅ **Risk Management**: Controlled drawdowns and volatility

## 🔧 API Management

### **Rate Limit Handling:**
- **Finnhub**: 50 calls/minute per key → 350 calls/minute total
- **TwelveData**: 8 calls/minute per key → 56 calls/minute total
- **Automatic Rotation**: Seamless switching between keys
- **Fallback System**: Multi-source redundancy

### **Testing & Monitoring:**
```bash
# Test all API keys
python test_api_keys.py

# Generate test data
python test_csv_generation.py
```

## 📊 Data Sources

- **Finnhub**: Primary real-time financial data
- **TwelveData**: Secondary data source for redundancy
- **MinIO**: Cloud storage for data persistence
- **GitHub Actions**: Automated data collection and processing

## 🛡️ Security & Best Practices

- ✅ **API Keys**: Stored as encrypted GitHub Secrets
- ✅ **Rate Limiting**: Intelligent usage management
- ✅ **Error Handling**: Robust fallback mechanisms
- ✅ **Logging**: Comprehensive monitoring and debugging
- ✅ **Version Control**: Clean git history with organized commits

## 📈 Next Steps

### **Immediate Enhancements:**
1. **Live Trading**: Implement paper trading integration
2. **More Symbols**: Expand to multi-asset portfolios
3. **Advanced Indicators**: Add additional technical signals
4. **Risk Management**: Enhanced position sizing algorithms

### **Advanced Features:**
1. **Machine Learning**: Predictive signal enhancement
2. **Portfolio Optimization**: Multi-asset allocation
3. **Real-time Alerts**: Trade notification system
4. **Performance Dashboard**: Web-based monitoring interface

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes with proper testing
4. Add documentation and examples
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

**🎉 Ready for Production!** Your enhanced trading system is now fully operational with enterprise-level API management and comprehensive performance analytics.

*Last Updated: August 19, 2025*
