document.addEventListener('DOMContentLoaded', function() {
    const backtestForm = document.getElementById('backtestForm');
    if (backtestForm) {
        backtestForm.addEventListener('submit', async function(event) {
            event.preventDefault();
            const form = event.target;
            const statusMessagesDiv = document.getElementById('statusMessages');
            const metricsResultDiv = document.getElementById('metricsResult').querySelector('pre');
            const tradesTableBody = document.getElementById('tradesResult').querySelector('tbody');

            statusMessagesDiv.textContent = 'Loading backtest results...';
            statusMessagesDiv.className = 'loading results-section'; // Reset classes
            metricsResultDiv.textContent = '';
            tradesTableBody.innerHTML = '<tr><td colspan="13">Loading trades...</td></tr>';

            const params = {
                symbol: form.symbol.value,
                interval: form.interval.value,
                category: form.category.value,
                data_limit: parseInt(form.data_limit.value),

                static_threshold_percent: parseFloat(form.fvg_static_threshold_percent.value),
                use_adaptive_threshold: form.fvg_use_adaptive_threshold.checked,
                use_volume_confirmation: form.fvg_use_volume_confirmation.checked,
                volume_lookback_period: parseInt(form.fvg_volume_lookback_period.value),
                volume_factor: parseFloat(form.fvg_volume_factor.value),
                min_fvg_price_height: parseFloat(form.fvg_min_price_height.value),

                initial_balance: parseFloat(form.initial_balance.value),
                // API expects commission_percent as a decimal, e.g., 0.00075 for 0.075%
                commission_percent: parseFloat(form.commission_percent.value) / 100,
                risk_per_trade_percent: parseFloat(form.risk_per_trade_percent.value),
                // API expects risk_free_rate_annual as a decimal, e.g., 0.02 for 2%
                risk_free_rate_annual: parseFloat(form.risk_free_rate_annual.value) / 100
            };

            try {
                const response = await fetch('/api/v1/backtest/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(params)
                });

                statusMessagesDiv.textContent = ''; // Clear loading

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: 'Failed to parse error response.' }));
                    throw new Error(`HTTP error ${response.status}: ${errorData.detail || response.statusText}`);
                }

                const results = await response.json();

                // Display Metrics
                let metricsText = '';
                if (results.performance_metrics) {
                    for (const key in results.performance_metrics) {
                        let value = results.performance_metrics[key];
                        if (typeof value === 'number' && !Number.isInteger(value)) {
                            value = parseFloat(value.toFixed(4));
                        }
                        metricsText += `${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${value}\n`;
                    }
                } else {
                    metricsText = "No performance metrics returned.";
                }
                metricsResultDiv.textContent = metricsText;

                // Display Trades
                tradesTableBody.innerHTML = ''; // Clear loading/previous trades
                if (results.trades && results.trades.length > 0) {
                    results.trades.forEach(trade => {
                        const row = tradesTableBody.insertRow();
                        row.insertCell().textContent = trade.fvg_type;
                        row.insertCell().textContent = new Date(trade.entry_time).toLocaleString();
                        row.insertCell().textContent = typeof trade.entry_price === 'number' ? trade.entry_price.toFixed(5) : trade.entry_price;
                        row.insertCell().textContent = new Date(trade.exit_time).toLocaleString();
                        row.insertCell().textContent = typeof trade.exit_price === 'number' ? trade.exit_price.toFixed(5) : trade.exit_price;
                        row.insertCell().textContent = typeof trade.sl_price === 'number' ? trade.sl_price.toFixed(5) : trade.sl_price;
                        row.insertCell().textContent = typeof trade.tp_price === 'number' ? trade.tp_price.toFixed(5) : trade.tp_price;
                        row.insertCell().textContent = trade.status;
                        row.insertCell().textContent = typeof trade.pnl_absolute === 'number' ? trade.pnl_absolute.toFixed(2) : trade.pnl_absolute;
                        row.insertCell().textContent = typeof trade.pnl_percent === 'number' ? trade.pnl_percent.toFixed(2) : trade.pnl_percent;
                        row.insertCell().textContent = typeof trade.commission_paid === 'number' ? trade.commission_paid.toFixed(4) : trade.commission_paid;
                        row.insertCell().textContent = typeof trade.position_size === 'number' ? trade.position_size.toFixed(4) : trade.position_size;
                        row.insertCell().textContent = typeof trade.amount_risked === 'number' ? trade.amount_risked.toFixed(2) : trade.amount_risked;
                        row.insertCell().textContent = typeof trade.balance_after_trade === 'number' ? trade.balance_after_trade.toFixed(2) : trade.balance_after_trade;
                    });
                } else {
                    tradesTableBody.innerHTML = '<tr><td colspan="13">No trades were executed in this backtest.</td></tr>';
                }
                statusMessagesDiv.textContent = 'Backtest completed successfully.';
                statusMessagesDiv.className = 'results-section';


            } catch (error) {
                metricsResultDiv.textContent = 'Error fetching or processing backtest results.';
                tradesTableBody.innerHTML = '<tr><td colspan="13">Error occurred.</td></tr>';
                statusMessagesDiv.textContent = `Error: ${error.message}`;
                statusMessagesDiv.className = 'error results-section';
                console.error('Backtest execution error:', error);
            }
        });
    } else {
        console.error('Backtest form not found!');
    }
});
