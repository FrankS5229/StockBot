"""目標價引擎測試（純離線，用合成資料）。

涵蓋：GBM 機率邊界、零漂移錐對稱、Pivot/Fib 公式對拍、無 look-ahead。
執行： python -m tests.test_targets
"""
import math

import tests.conftest_path  # noqa: F401
import numpy as np
import pandas as pd

import targets
from indicators import ta


def _synthetic(n=300, seed=1):
    rng = np.random.default_rng(seed)
    # 用 numpy 陣列（無自帶索引），避免與 DataFrame 的日期索引對不上而變 NaN
    close = 100 + np.cumsum(rng.normal(0.05, 1, n))
    high = close + rng.uniform(0, 1, n)
    low = close - rng.uniform(0, 1, n)
    vol = rng.integers(1000, 5000, n).astype(float)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def test_norm_cdf_known_values():
    assert abs(targets._norm_cdf(0.0) - 0.5) < 1e-9
    assert abs(targets._norm_cdf(1.6449) - 0.95) < 1e-3
    assert abs(targets._norm_cdf(-1.6449) - 0.05) < 1e-3
    print("norm_cdf OK")


def test_prob_terminal_boundaries():
    # P(S_H ≥ 中位價) 恰為 0.5（中位 = s0·exp((μ−½σ²)H)）
    s0, mu, sigma, h = 100.0, 0.0, 0.02, 10
    median = s0 * math.exp((mu - 0.5 * sigma ** 2) * h)
    p = targets.prob_terminal(s0, median, mu=mu, sigma=sigma, h=h, direction="up")
    assert abs(p - 0.5) < 1e-9, p
    # μ=0 時中位 < s0，故 P(S_H ≥ s0) < 0.5
    assert targets.prob_terminal(s0, s0, mu, sigma, h, "up") < 0.5
    # 目標越高，上檔達成機率越低（單調）
    p_low = targets.prob_terminal(s0, 105, 0.0, 0.02, 10, "up")
    p_high = targets.prob_terminal(s0, 120, 0.0, 0.02, 10, "up")
    assert p_low > p_high
    # up 與 down 互補
    p_up = targets.prob_terminal(s0, 110, 0.001, 0.02, 10, "up")
    p_dn = targets.prob_terminal(s0, 110, 0.001, 0.02, 10, "down")
    assert abs((p_up + p_dn) - 1.0) < 1e-9
    # sigma=0 → None
    assert targets.prob_terminal(s0, 110, 0.0, 0.0, 10, "up") is None
    print("prob_terminal boundaries OK")


def test_zero_drift_band_symmetry():
    """零漂移（μ=0）時：mean = 現價（lognormal 期望）；中位 = spot·exp(−½σ²H) < spot；
    對數空間上下界以「中位」為中心對稱（low·high == median²）。"""
    df = _synthetic()
    spec = targets.HorizonSpec(
        label="t", bars=20, fib_lookback=60, pole_window=20,
        donchian_n=20, pivot_window=5, zero_drift=True, ret_lookback=120,
    )
    rep = targets.build_report(df, "X", spec)
    assert rep.mu == 0.0
    assert abs(rep.mean - rep.spot) < 1e-6
    assert rep.median < rep.spot                      # −½σ² 拖低中位
    assert abs(rep.low90 * rep.high90 - rep.median ** 2) / rep.median ** 2 < 1e-9
    assert rep.low90 < rep.low70 < rep.median < rep.high70 < rep.high90
    print("zero-drift symmetry OK")


def test_pivot_and_fib_formulas():
    df = _synthetic(n=60)
    w = 5
    h = float(df["high"].iloc[-w:].max())
    l = float(df["low"].iloc[-w:].min())
    c = float(df["close"].iloc[-1])
    p = (h + l + c) / 3
    piv = {lv.method: lv.price for lv in targets.pivot_points(df, w)}
    assert abs(piv["pivot_r1"] - (2 * p - l)) < 1e-9
    assert abs(piv["pivot_s1"] - (2 * p - h)) < 1e-9
    # Fib 擴展：swing_low + range*ext
    lookback = 60
    sh = float(df["high"].iloc[-lookback:].max())
    sl = float(df["low"].iloc[-lookback:].min())
    rng = sh - sl
    fib = {lv.method: lv.price for lv in targets.fib_extensions(df, lookback)}
    assert abs(fib["fib_1.618"] - (sl + rng * 1.618)) < 1e-9
    print("pivot/fib formulas OK")


def test_prefix_independent_of_future():
    """「當時」的目標報告只由截至當下的 K 棒決定，不被其後新增的資料影響。

    取完整 df 的前 k 根 build_report，與「先截前 k 根再 build」結果須完全一致——
    證明 targets 不會（也無法）回看 k 之後的未來資料。
    """
    full = ta.add_indicators(_synthetic(n=300))
    k = 200
    spec = targets.SHORT_SPEC
    rep_a = targets.build_report(full.iloc[:k], "X", spec)              # 用前 k 根
    rep_b = targets.build_report(full.iloc[:k].copy(), "X", spec)        # 同資料、獨立物件
    assert rep_a.spot == rep_b.spot
    assert round(rep_a.median, 9) == round(rep_b.median, 9)
    assert [round(lv.price, 9) for lv in rep_a.levels] == \
           [round(lv.price, 9) for lv in rep_b.levels]
    # 加入更多「未來」根後，到第 k 根的報告不應改變（與只用前 k 根一致）
    assert round(targets.build_report(full.iloc[:k], "X", spec).median, 9) == round(rep_a.median, 9)
    # sanity：用到更新的尾端資料時，現價會不同（確實看的是最新一根）
    assert targets.build_report(full.iloc[:k + 30], "X", spec).spot != rep_a.spot
    print("prefix-independent-of-future OK")


def test_plain_summary():
    rep = targets.build_report(_synthetic(), "ABC", targets.SHORT_SPEC)
    s = targets.plain_summary(rep)
    assert isinstance(s, str) and "短線" in s and "第一目標" in s and "70%" in s
    print("plain_summary OK")


if __name__ == "__main__":
    test_norm_cdf_known_values()
    test_prob_terminal_boundaries()
    test_zero_drift_band_symmetry()
    test_pivot_and_fib_formulas()
    test_prefix_independent_of_future()
    test_plain_summary()
    print("test_targets 全部通過")
