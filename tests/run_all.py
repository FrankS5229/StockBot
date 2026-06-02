"""一次跑完所有測試。

執行：
    python -m tests.run_all            # 含連網測試
    python -m tests.run_all --offline  # 只跑離線測試
"""
import sys

import tests.conftest_path  # noqa: F401


def main():
    offline = "--offline" in sys.argv
    from tests import test_indicators, test_strategy, test_backtest, test_data, test_core

    print("=== indicators ===")
    for fn in [
        test_indicators.test_ema_matches_pandas,
        test_indicators.test_rsi_bounds,
        test_indicators.test_macd_hist_identity,
        test_indicators.test_bbands_order,
        test_indicators.test_atr_positive,
        test_indicators.test_add_indicators_columns,
    ]:
        fn()

    print("=== strategy ===")
    test_strategy.test_signal_columns_and_values()
    test_strategy.test_buy_has_reason_and_stops()
    test_strategy.test_missing_indicator_raises()
    test_strategy.test_fibonacci_columns_and_values()
    test_strategy.test_fibonacci_buy_stops()
    test_strategy.test_fibonacci_missing_indicator_raises()
    test_strategy.test_golden_cross_columns_and_values()
    test_strategy.test_golden_cross_buy_on_crossover()
    test_strategy.test_golden_cross_missing_close_raises()
    test_strategy.test_bollinger_columns_and_values()
    test_strategy.test_bollinger_buy_stops()
    test_strategy.test_bollinger_missing_indicator_raises()

    print("=== core ===")
    test_core.test_strategy_registry()
    test_core.test_portfolio_crud()
    test_core.test_get_portfolio_holdings_user_priority()

    print("=== backtest ===")
    test_backtest.test_next_bar_execution_and_profit()
    test_backtest.test_cost_reduces_return()
    test_backtest.test_no_signal_flat()
    test_backtest.test_split()

    print("=== data ===")
    test_data.test_standardize_offline()
    if not offline:
        test_data.test_fetch_online()

    print("\nALL_TESTS_PASSED")


if __name__ == "__main__":
    main()
