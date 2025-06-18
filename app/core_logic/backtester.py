import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta # Added timedelta
from app.core_logic import fvg_detector
import numpy as np # Added numpy

def run_backtest(
    ohlcv_df: pd.DataFrame,
    fvg_detection_threshold_percent: float = 0.0,
    initial_balance: float = 10000.0, # Added
    commission_percent: float = 0.00075, # 0.075%
    risk_free_rate_annual: float = 0.0 # Added
) -> Dict[str, Any]:

    if not isinstance(ohlcv_df, pd.DataFrame) or ohlcv_df.empty or len(ohlcv_df) < 3:
        return {"trades": [], "performance_metrics": {
            "error": "Input DataFrame is invalid or too short."
        }}

    # Ensure DataFrame has necessary columns and correct data types
    required_cols = ['time', 'open', 'high', 'low', 'close']
    if not all(col in ohlcv_df.columns for col in required_cols):
        raise ValueError(f"OHLCV DataFrame must contain columns: {required_cols}")

    df = ohlcv_df.copy() # Work on a copy

    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['time'] = pd.to_datetime(df['time'])

    df.dropna(subset=required_cols, inplace=True)
    if len(df) < 3:
        return {"trades": [], "performance_metrics": {
             "error": "DataFrame too short after cleaning."
        }}

    potential_fvgs = fvg_detector.detect_fvgs(
        df,
        threshold_percent=fvg_detection_threshold_percent
    )

    potential_fvgs.sort(key=lambda x: x['trigger_candle_time'])

    processed_fvg_idx = 0
    simulated_trades: List[Dict] = []
    current_trade: Optional[Dict] = None

    for i in range(len(df)):
        current_candle = df.iloc[i]
        candle_time = current_candle['time']
        candle_high = current_candle['high']
        candle_low = current_candle['low']

        if current_trade:
            exit_price = None
            status = None
            trade_type = current_trade['fvg_type']
            sl = current_trade['sl_price']
            tp = current_trade['tp_price']

            if trade_type == 'bullish':
                if candle_low <= sl: exit_price, status = sl, "SL"
                elif candle_high >= tp: exit_price, status = tp, "TP"
            elif trade_type == 'bearish':
                if candle_high >= sl: exit_price, status = sl, "SL"
                elif candle_low <= tp: exit_price, status = tp, "TP"

            if exit_price is not None and status is not None:
                entry_price = current_trade['entry_price']
                position_size = 1.0

                commission_on_entry = entry_price * position_size * commission_percent
                commission_on_exit = exit_price * position_size * commission_percent
                total_commission = commission_on_entry + commission_on_exit

                pnl_gross = (exit_price - entry_price) * position_size if trade_type == 'bullish' else (entry_price - exit_price) * position_size
                pnl_net_absolute = pnl_gross - total_commission
                initial_position_value = entry_price * position_size
                pnl_net_percent = (pnl_net_absolute / initial_position_value) * 100 if initial_position_value != 0 else 0

                simulated_trades.append({
                    "fvg_type": trade_type, "entry_time": current_trade['entry_time'],
                    "entry_price": entry_price, "exit_time": candle_time,
                    "exit_price": exit_price, "sl_price": sl, "tp_price": tp,
                    "status": status, "pnl_absolute": pnl_net_absolute,
                    "pnl_percent": pnl_net_percent, "commission_paid": total_commission,
                })
                current_trade = None

        if current_trade is None:
            for j in range(processed_fvg_idx, len(potential_fvgs)):
                fvg = potential_fvgs[j]
                if fvg['trigger_candle_time'] > candle_time: break

                entry_price_target = fvg['entry_price']
                actual_entry_price_for_trade = None

                if candle_low <= entry_price_target <= candle_high:
                    actual_entry_price_for_trade = entry_price_target

                if actual_entry_price_for_trade is not None:
                    current_trade = {
                        "fvg_type": fvg['fvg_type'], "entry_price": actual_entry_price_for_trade,
                        "sl_price": fvg['sl_price'], "tp_price": fvg['tp_price'],
                        "entry_time": candle_time, "fvg_details": fvg
                    }
                    processed_fvg_idx = j + 1
                    break

    # Call calculate_performance_metrics
    metrics_results = calculate_performance_metrics(
        simulated_trades,
        initial_balance,
        risk_free_rate_annual
    )

    return {
        "trades": simulated_trades,
        "performance_metrics": metrics_results
    }

def calculate_performance_metrics(
    trades: List[Dict[str, Any]],
    initial_balance: float,
    risk_free_rate_annual: float = 0.0
) -> Dict[str, Any]:

    metrics: Dict[str, Any] = {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0, "neutral_trades": 0,
        "win_rate_percent": 0.0, "loss_rate_percent": 0.0, "profit_factor": 0.0,
        "total_net_pnl_absolute": 0.0,
        "average_pnl_per_trade_absolute": 0.0,
        "average_profit_per_winning_trade_absolute": 0.0,
        "average_loss_per_losing_trade_absolute": 0.0,
        "average_holding_time_hours": 0.0,
        "sharpe_ratio_simplified": 0.0, # Simplified Sharpe
        "max_drawdown_percent": 0.0,
        "final_equity": initial_balance,
        "peak_equity": initial_balance,
        "buy_and_hold_return_percent": 0.0 # Placeholder
    }

    if not trades:
        return metrics

    total_trades = len(trades)
    winning_trades = 0
    losing_trades = 0
    neutral_trades = 0
    gross_profit = 0.0
    gross_loss = 0.0
    total_net_pnl_absolute = 0.0
    total_holding_time_seconds = 0.0

    pnl_percentages_for_sharpe = []

    for trade in trades:
        total_net_pnl_absolute += trade['pnl_absolute']
        pnl_percentages_for_sharpe.append(trade['pnl_percent'])

        if trade['pnl_absolute'] > 0:
            winning_trades += 1
            gross_profit += trade['pnl_absolute']
        elif trade['pnl_absolute'] < 0:
            losing_trades += 1
            gross_loss += trade['pnl_absolute']
        else:
            neutral_trades +=1

        entry_time = pd.to_datetime(trade['entry_time'])
        exit_time = pd.to_datetime(trade['exit_time'])
        if exit_time > entry_time: # Ensure valid time difference
             holding_time = (exit_time - entry_time).total_seconds()
             total_holding_time_seconds += holding_time

    metrics["total_trades"] = total_trades
    metrics["winning_trades"] = winning_trades
    metrics["losing_trades"] = losing_trades
    metrics["neutral_trades"] = neutral_trades
    metrics["total_net_pnl_absolute"] = total_net_pnl_absolute

    if total_trades > 0:
        metrics["win_rate_percent"] = (winning_trades / total_trades) * 100 if total_trades > winning_trades + losing_trades else (winning_trades / (winning_trades + losing_trades) * 100) if (winning_trades + losing_trades) > 0 else 0
        metrics["loss_rate_percent"] = (losing_trades / total_trades) * 100 if total_trades > winning_trades + losing_trades else (losing_trades / (winning_trades + losing_trades) * 100) if (winning_trades + losing_trades) > 0 else 0
        metrics["average_pnl_per_trade_absolute"] = total_net_pnl_absolute / total_trades
        if total_holding_time_seconds > 0:
             metrics["average_holding_time_hours"] = (total_holding_time_seconds / total_trades) / 3600

    if winning_trades > 0:
        metrics["average_profit_per_winning_trade_absolute"] = gross_profit / winning_trades

    if losing_trades > 0:
        metrics["average_loss_per_losing_trade_absolute"] = gross_loss / losing_trades

    if abs(gross_loss) > 0:
        metrics["profit_factor"] = gross_profit / abs(gross_loss)
    elif gross_profit > 0 :
        metrics["profit_factor"] = float('inf')
    else:
        metrics["profit_factor"] = 1.0 if total_net_pnl_absolute == 0 else 0.0


    if len(pnl_percentages_for_sharpe) > 1:
        mean_trade_percent_return = np.mean(pnl_percentages_for_sharpe)
        std_dev_trade_percent_return = np.std(pnl_percentages_for_sharpe)
        if std_dev_trade_percent_return > 0:
            # This is a simplified Sharpe Ratio based on per-trade percentage returns.
            # It does not account for annualization or the specific timing/duration of trades for risk_free_rate.
            # A common simplification is (Mean of returns) / (StdDev of returns), assuming 0 risk-free rate
            # or that returns are already excess returns.
            # If risk_free_rate_annual is non-zero, it should ideally be scaled to the avg trade duration.
            # For now, we'll calculate a simple version ignoring RFR for this simplified ratio.
            metrics["sharpe_ratio_simplified"] = mean_trade_percent_return / std_dev_trade_percent_return

    equity = initial_balance
    peak_equity = initial_balance
    max_drawdown_percent = 0.0

    # Sort trades by exit_time to correctly calculate equity curve and drawdown
    # The trades list is already sorted by exit_time as they are appended when closed.
    for trade in trades:
        equity += trade['pnl_absolute']
        if equity > peak_equity:
            peak_equity = equity

        if peak_equity > 0:
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown_percent:
                max_drawdown_percent = drawdown

    metrics["max_drawdown_percent"] = max_drawdown_percent * 100
    metrics["final_equity"] = equity
    metrics["peak_equity"] = peak_equity

    return metrics
