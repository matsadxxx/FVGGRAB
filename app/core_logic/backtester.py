"""
Core logic for backtesting Fair Value Gap (FVG) trading strategies.

This module provides functions to simulate trading based on detected FVGs
from historical OHLCV data and then calculate performance metrics based on
the simulated trades.
"""
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from app.core_logic import fvg_detector # Assuming fvg_detector has the latest signature
import numpy as np
import logging

logger = logging.getLogger(__name__)

def run_backtest(
    ohlcv_df: pd.DataFrame,
    # FVG detection parameters to be passed to detect_fvgs
    static_threshold_percent: float = 0.0, # Renamed from fvg_detection_threshold_percent
    use_adaptive_threshold: bool = False,
    adaptive_threshold_period_UNUSED: int = 0, # Matching detect_fvgs
    use_volume_confirmation: bool = False,
    volume_lookback_period: int = 20,
    volume_factor: float = 1.5,
    min_fvg_price_height: float = 0.0,
    # Backtester specific parameters
    initial_balance: float = 10000.0,
    commission_percent: float = 0.00075,
    risk_per_trade_percent: float = 1.0, # Percentage of current balance to risk
    risk_free_rate_annual: float = 0.0
) -> Dict[str, Any]:
    """
    Runs a backtest of an FVG-based trading strategy with risk-based position sizing.

    Args:
        ohlcv_df (pd.DataFrame): DataFrame with OHLCV data.
        static_threshold_percent (float): Static FVG body threshold.
        use_adaptive_threshold (bool): Use adaptive FVG body threshold.
        adaptive_threshold_period_UNUSED (int): Placeholder for adaptive logic.
        use_volume_confirmation (bool): Use FVG volume confirmation.
        volume_lookback_period (int): Lookback for volume average.
        volume_factor (float): Volume multiplier for confirmation.
        min_fvg_price_height (float): Minimum FVG gap height.
        initial_balance (float): Starting balance.
        commission_percent (float): Commission rate per trade side.
        risk_per_trade_percent (float): Percentage of balance to risk per trade.
        risk_free_rate_annual (float): Annual risk-free rate for metrics.

    Returns:
        Dict[str, Any]: Contains 'trades' list and 'performance_metrics' dictionary.
    """
    # TODO: Implement more advanced order execution simulation (e.g., slippage model).
    # TODO: Add logic to handle trades open at the end of historical data.
    # TODO: Consider FVG expiration if not entered within N candles.

    if not isinstance(ohlcv_df, pd.DataFrame) or ohlcv_df.empty or len(ohlcv_df) < 3:
        logger.error("Input DataFrame is invalid or too short for backtesting.")
        return {"trades": [], "performance_metrics": {"error": "Input DataFrame is invalid or too short."}}

    required_cols = ['time', 'open', 'high', 'low', 'close', 'volume'] # Ensure volume is present for fvg_detector
    if not all(col in ohlcv_df.columns for col in required_cols):
        raise ValueError(f"OHLCV DataFrame must contain columns: {required_cols}")

    df = ohlcv_df.copy()

    for col in ['open', 'high', 'low', 'close', 'volume']: # Ensure volume is also numeric
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['time'] = pd.to_datetime(df['time'])

    df.dropna(subset=required_cols, inplace=True) # Drop rows if any essential data became NaN
    if len(df) < 3:
        logger.error("DataFrame too short after cleaning NaNs for backtesting.")
        return {"trades": [], "performance_metrics": {"error": "DataFrame too short after cleaning."}}

    potential_fvgs = fvg_detector.detect_fvgs(
        df, # Pass the cleaned df
        static_threshold_percent=static_threshold_percent,
        use_adaptive_threshold=use_adaptive_threshold,
        adaptive_threshold_period_UNUSED=adaptive_threshold_period_UNUSED,
        use_volume_confirmation=use_volume_confirmation,
        volume_lookback_period=volume_lookback_period,
        volume_factor=volume_factor,
        min_fvg_price_height=min_fvg_price_height
    )

    potential_fvgs.sort(key=lambda x: pd.to_datetime(x['trigger_candle_time'])) # Ensure sorting by datetime

    processed_fvg_idx = 0
    simulated_trades: List[Dict] = []
    current_trade: Optional[Dict] = None
    current_balance = initial_balance

    logger.info(f"Starting backtest. Initial balance: {initial_balance:.2f}")

    for i in range(len(df)):
        current_candle = df.iloc[i]
        candle_time = current_candle['time']
        candle_high = current_candle['high']
        candle_low = current_candle['low']

        if current_trade:
            exit_price = None
            status = None
            trade_type = current_trade['fvg_type']
            sl_target = current_trade['sl_price']
            tp_target = current_trade['tp_price']
            entry_price = current_trade['entry_price']
            position_size = current_trade['position_size']
            amount_risked = current_trade['amount_risked']

            if trade_type == 'bullish':
                if candle_low <= sl_target: exit_price, status = sl_target, "SL"
                elif candle_high >= tp_target: exit_price, status = tp_target, "TP"
            elif trade_type == 'bearish':
                if candle_high >= sl_target: exit_price, status = sl_target, "SL"
                elif candle_low <= tp_target: exit_price, status = tp_target, "TP"

            if exit_price is not None and status is not None:
                commission_on_entry = entry_price * position_size * commission_percent
                commission_on_exit = exit_price * position_size * commission_percent
                total_commission_for_trade = commission_on_entry + commission_on_exit

                gross_pnl_for_trade = (exit_price - entry_price) * position_size if trade_type == 'bullish' else (entry_price - exit_price) * position_size
                net_pnl_absolute_for_trade = gross_pnl_for_trade - total_commission_for_trade

                pnl_percent_on_risked_capital = (net_pnl_absolute_for_trade / amount_risked) * 100 if amount_risked != 0 else 0

                current_balance += net_pnl_absolute_for_trade
                logger.debug(f"Trade closed: {status} at {exit_price:.2f}. PNL: {net_pnl_absolute_for_trade:.2f}. Balance: {current_balance:.2f}")

                simulated_trades.append({
                    "fvg_type": trade_type, "entry_time": pd.to_datetime(current_trade['entry_time']),
                    "entry_price": entry_price, "exit_time": pd.to_datetime(candle_time),
                    "exit_price": exit_price, "sl_price": sl_target, "tp_price": tp_target,
                    "status": status, "pnl_absolute": net_pnl_absolute_for_trade,
                    "pnl_percent": pnl_percent_on_risked_capital,
                    "commission_paid": total_commission_for_trade,
                    "position_size": position_size, "amount_risked": amount_risked,
                    "balance_after_trade": current_balance
                })
                current_trade = None

        if current_trade is None:
            if current_balance <= 0:
                logger.warning(f"Balance is {current_balance:.2f} at {candle_time}, cannot open new trades.")
                continue

            risk_amount_for_new_trade = current_balance * (risk_per_trade_percent / 100.0)
            if risk_amount_for_new_trade <= 0:
                logger.info(f"Calculated risk amount is {risk_amount_for_new_trade:.2f} at {candle_time}, skipping trade consideration.")
                continue

            for j in range(processed_fvg_idx, len(potential_fvgs)):
                fvg = potential_fvgs[j]
                if pd.to_datetime(fvg['trigger_candle_time']) > candle_time: break

                entry_price_target = fvg['entry_price']
                sl_price_fvg = fvg['sl_price']
                actual_entry_price_for_trade = None

                if candle_low <= entry_price_target <= candle_high:
                    actual_entry_price_for_trade = entry_price_target

                if actual_entry_price_for_trade is not None:
                    distance_to_sl = abs(actual_entry_price_for_trade - sl_price_fvg)

                    if distance_to_sl <= 1e-9: # Use a small epsilon for float comparison
                        logger.warning(f"Trade on FVG at {fvg['time']} for {fvg['fvg_type']} skipped: distance to SL is effectively zero ({distance_to_sl:.4f}).")
                        # Mark as processed to avoid re-evaluating this specific FVG constantly if it's problematic
                        # If we don't advance processed_fvg_idx, and this FVG keeps appearing, it could loop.
                        # However, if it's simply not enterable, we might want to see other FVGs for this candle.
                        # For now, let's assume such an FVG is "bad" and move past it by advancing j.
                        # The outer loop will re-evaluate from the new processed_fvg_idx if we 'continue' here.
                        # To ensure we don't get stuck on this FVG if it's the one at processed_fvg_idx:
                        if j == processed_fvg_idx: processed_fvg_idx = j + 1
                        continue

                    position_size = risk_amount_for_new_trade / distance_to_sl

                    current_trade = {
                        "fvg_type": fvg['fvg_type'], "entry_price": actual_entry_price_for_trade,
                        "sl_price": sl_price_fvg, "tp_price": fvg['tp_price'],
                        "entry_time": candle_time, "fvg_details": fvg,
                        "position_size": position_size, "amount_risked": risk_amount_for_new_trade
                    }
                    processed_fvg_idx = j + 1
                    logger.debug(f"Trade opened: {fvg['fvg_type']} at {actual_entry_price_for_trade:.2f}. Size: {position_size:.4f}. SL: {sl_price_fvg:.2f}. Risked: {risk_amount_for_new_trade:.2f}")
                    break

    logger.info(f"Backtest finished. Total trades: {len(simulated_trades)}. Final balance: {current_balance:.2f}")
    metrics_results = calculate_performance_metrics(
        trades=simulated_trades, initial_balance=initial_balance,
        risk_free_rate_annual=risk_free_rate_annual
    )
    return {"trades": simulated_trades, "performance_metrics": metrics_results}

def calculate_performance_metrics(
    trades: List[Dict[str, Any]], initial_balance: float,
    risk_free_rate_annual: float = 0.0,
) -> Dict[str, Any]:
    # ... (Implementation as before) ...
    metrics: Dict[str, Any] = {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0, "neutral_trades": 0,
        "win_rate_percent": 0.0, "loss_rate_percent": 0.0, "profit_factor": 0.0,
        "total_net_pnl_absolute": 0.0,
        "average_pnl_per_trade_absolute": 0.0,
        "average_profit_per_winning_trade_absolute": 0.0,
        "average_loss_per_losing_trade_absolute": 0.0,
        "average_holding_time_hours": 0.0,
        "sharpe_ratio_simplified": 0.0,
        "max_drawdown_percent": 0.0,
        "final_equity": initial_balance,
        "peak_equity": initial_balance,
        "buy_and_hold_return_percent": 0.0, # Placeholder
        "total_commission_paid": 0.0
    }
    if not trades: return metrics
    total_trades = len(trades)
    winning_trades, losing_trades, neutral_trades = 0, 0, 0
    gross_profit, gross_loss, total_net_pnl_absolute, total_holding_time_seconds, total_commission_paid_sum = 0.0, 0.0, 0.0, 0.0, 0.0
    pnl_percentages_for_sharpe = []

    for trade in trades:
        total_net_pnl_absolute += trade['pnl_absolute']
        pnl_percentages_for_sharpe.append(trade['pnl_percent'])
        total_commission_paid_sum += trade['commission_paid']
        if trade['pnl_absolute'] > 0: winning_trades += 1; gross_profit += trade['pnl_absolute']
        elif trade['pnl_absolute'] < 0: losing_trades += 1; gross_loss += trade['pnl_absolute']
        else: neutral_trades +=1
        entry_time = pd.to_datetime(trade['entry_time'])
        exit_time = pd.to_datetime(trade['exit_time'])
        if exit_time > entry_time: total_holding_time_seconds += (exit_time - entry_time).total_seconds()

    metrics.update({
        "total_trades": total_trades, "winning_trades": winning_trades, "losing_trades": losing_trades,
        "neutral_trades": neutral_trades, "total_net_pnl_absolute": total_net_pnl_absolute,
        "total_commission_paid": total_commission_paid_sum
    })
    if total_trades > 0:
        non_neutral_trades = winning_trades + losing_trades
        if non_neutral_trades > 0:
            metrics["win_rate_percent"] = (winning_trades / non_neutral_trades) * 100
            metrics["loss_rate_percent"] = (losing_trades / non_neutral_trades) * 100
        metrics["average_pnl_per_trade_absolute"] = total_net_pnl_absolute / total_trades
        if total_holding_time_seconds > 0:
             metrics["average_holding_time_hours"] = (total_holding_time_seconds / total_trades) / 3600.0
    if winning_trades > 0: metrics["average_profit_per_winning_trade_absolute"] = gross_profit / winning_trades
    if losing_trades > 0: metrics["average_loss_per_losing_trade_absolute"] = gross_loss / losing_trades
    if abs(gross_loss) > 0: metrics["profit_factor"] = gross_profit / abs(gross_loss)
    elif gross_profit > 0: metrics["profit_factor"] = float('inf')
    else: metrics["profit_factor"] = 1.0 if total_net_pnl_absolute == 0 else 0.0
    if len(pnl_percentages_for_sharpe) > 1:
        mean_return = np.mean(pnl_percentages_for_sharpe)
        std_return = np.std(pnl_percentages_for_sharpe)
        if std_return > 1e-9: metrics["sharpe_ratio_simplified"] = mean_return / std_return

    current_equity, peak_equity, max_drawdown_val = initial_balance, initial_balance, 0.0
    for trade in trades:
        current_equity += trade['pnl_absolute']
        if current_equity > peak_equity: peak_equity = current_equity
        drawdown = peak_equity - current_equity
        if drawdown > max_drawdown_val: max_drawdown_val = drawdown
    if peak_equity > 0 : metrics["max_drawdown_percent"] = (max_drawdown_val / peak_equity) * 100
    elif initial_balance > 0 : metrics["max_drawdown_percent"] = (max_drawdown_val / initial_balance) * 100
    metrics["final_equity"], metrics["peak_equity"] = current_equity, peak_equity
    return metrics
