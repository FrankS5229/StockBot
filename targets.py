"""目標價引擎：前瞻式價格情境（技術價位 ＋ 統計投影），輸出區間與達成機率。

與策略 buy/sell **解耦**——策略是「K 線走完後事後標註」進出場，這裡是「從當下往前看」
估算未來 H 根 K 棒後可能到的價位。所有計算只用到當下與過去 K 棒（無 look-ahead）。

兩類方法：
- 技術價位法（規則明確、可解釋）：
    * Pivot Points（古典樞紐，R1–R3 上檔／S1–S3 下檔）
    * Fibonacci 擴展（1.272 / 1.618 / 2.618）
    * 量度移動 Measured Move（前波幅度的 70% / 100% / 120% → 保守/基準/樂觀）
    * 通道（Bollinger 上軌/中軌、Donchian N 日高）
- 統計投影法（Geometric Brownian Motion，漂移 μ ＋ 波動 σ）：
    由對數報酬估 μ/σ，給期望/中位價與 70%/90% 信賴區間；
    並以常態 CDF 替「每一條技術目標價」算出「H 根後收在其上(up)/其下(down)的機率」，
    把兩類方法串成使用者要的「區間 ＋ 機率」。

數學參考：
    GBM 下 ln(S_H) ~ Normal( ln S0 + (μ−½σ²)H , σ²H )
    分位數：  S0 · exp((μ−½σ²)H ± z·σ·√H)
    達成機率：P(S_H ≥ T) = Φ( (ln(S0/T) + (μ−½σ²)H) / (σ√H) )
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# 兩側信賴區間對應的 z 值：70% → 各尾 15% → 0.85 分位；90% → 各尾 5% → 0.95 分位
_Z70 = 1.0364
_Z90 = 1.6449


@dataclass
class HorizonSpec:
    """一個 horizon（短線/長線）的參數組（以「K 棒根數」為單位）。"""

    label: str          # 顯示名（短線 / 長線）
    bars: int           # 投影展望根數 H
    fib_lookback: int   # Fibonacci 取波段高低的回看根數
    pole_window: int    # 量度移動取「前波幅度」的回看根數
    donchian_n: int     # Donchian 通道高的回看根數
    pivot_window: int   # 古典樞紐聚合 H/L/C 的回看根數
    zero_drift: bool     # 是否採零漂移（μ=0，純波動錐；長線預設較保險）
    ret_lookback: int = 252  # 估 μ/σ 的對數報酬回看根數


# 日線導向的預設；盤中週期由呼叫端依比例覆寫 bars。
SHORT_SPEC = HorizonSpec(
    label="短線", bars=10, fib_lookback=60, pole_window=20,
    donchian_n=20, pivot_window=5, zero_drift=False, ret_lookback=120,
)
LONG_SPEC = HorizonSpec(
    label="長線", bars=120, fib_lookback=120, pole_window=60,
    donchian_n=55, pivot_window=21, zero_drift=True, ret_lookback=252,
)


@dataclass
class TargetLevel:
    method: str                       # 方法 key（pivot_r1 / fib_1.618 / measured_base ...）
    label: str                        # 白話標籤
    price: float                      # 目標價
    direction: str                    # "up" / "down"
    prob_reach: float | None = None   # GBM 估「期末收在其上(up)/其下(down)」機率


@dataclass
class TargetReport:
    symbol: str
    horizon_label: str
    horizon_bars: int
    spot: float
    # 統計帶（GBM）
    median: float
    mean: float
    low70: float
    high70: float
    low90: float
    high90: float
    mu: float            # 每根對數報酬漂移
    sigma: float         # 每根對數報酬波動
    zero_drift: bool
    levels: list[TargetLevel] = field(default_factory=list)
    # 彙整三檔上檔目標
    conservative: float | None = None
    base: float | None = None
    optimistic: float | None = None


# --------------------------------------------------------------------------- #
# 統計投影（GBM）
# --------------------------------------------------------------------------- #
def _norm_cdf(x: float) -> float:
    """標準常態 CDF（用 math.erf，免 scipy 相依）。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def gbm_params(close: pd.Series, *, ret_lookback: int = 252, zero_drift: bool = False):
    """由對數報酬估每根漂移 μ 與波動 σ。zero_drift=True 時 μ 強制 0。"""
    r = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    if ret_lookback and len(r) > ret_lookback:
        r = r.iloc[-ret_lookback:]
    mu = 0.0 if zero_drift else (float(r.mean()) if len(r) else 0.0)
    sigma = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    return mu, sigma


def prob_terminal(s0: float, t: float, mu: float, sigma: float, h: int, direction: str) -> float | None:
    """GBM 下，H 根後期末價收在 T 之上(up)/之下(down)的機率。"""
    if sigma <= 0 or h <= 0 or s0 <= 0 or t <= 0:
        return None
    drift = (mu - 0.5 * sigma ** 2) * h
    denom = sigma * math.sqrt(h)
    z = (math.log(s0 / t) + drift) / denom   # P(S_H ≥ T)
    p_up = _norm_cdf(z)
    return p_up if direction == "up" else 1.0 - p_up


# --------------------------------------------------------------------------- #
# 技術價位
# --------------------------------------------------------------------------- #
def pivot_points(df: pd.DataFrame, window: int) -> list[TargetLevel]:
    """古典樞紐：以最近 window 根聚合 H/L/C。R 系列＝上檔、S 系列＝下檔。"""
    w = max(2, min(window, len(df)))
    h = float(df["high"].iloc[-w:].max())
    l = float(df["low"].iloc[-w:].min())
    c = float(df["close"].iloc[-1])
    p = (h + l + c) / 3.0
    rng = h - l
    out = [
        TargetLevel("pivot_r1", "樞紐 R1（第一上檔）", 2 * p - l, "up"),
        TargetLevel("pivot_r2", "樞紐 R2（第二上檔）", p + rng, "up"),
        TargetLevel("pivot_r3", "樞紐 R3（第三上檔）", h + 2 * (p - l), "up"),
        TargetLevel("pivot_s1", "樞紐 S1（第一下檔）", 2 * p - h, "down"),
        TargetLevel("pivot_s2", "樞紐 S2（第二下檔）", p - rng, "down"),
        TargetLevel("pivot_s3", "樞紐 S3（第三下檔）", l - 2 * (h - p), "down"),
    ]
    return out


def fib_extensions(df: pd.DataFrame, lookback: int) -> list[TargetLevel]:
    """Fibonacci 擴展：自最近 lookback 根的波段低點往上投影 1.272/1.618/2.618。"""
    w = max(2, min(lookback, len(df)))
    swing_high = float(df["high"].iloc[-w:].max())
    swing_low = float(df["low"].iloc[-w:].min())
    rng = swing_high - swing_low
    if rng <= 0:
        return []
    out = []
    for ext in (1.272, 1.618, 2.618):
        out.append(
            TargetLevel(f"fib_{ext}", f"Fib 擴展 {ext:g}", swing_low + rng * ext, "up")
        )
    return out


def measured_move(df: pd.DataFrame, pole_window: int) -> list[TargetLevel]:
    """量度移動：以最近 pole_window 根的波段幅度（pole）自當前價往上投影 70/100/120%。"""
    w = max(2, min(pole_window, len(df)))
    pole = float(df["high"].iloc[-w:].max() - df["low"].iloc[-w:].min())
    spot = float(df["close"].iloc[-1])
    if pole <= 0:
        return []
    return [
        TargetLevel("measured_conservative", "量度移動 70%（保守）", spot + pole * 0.7, "up"),
        TargetLevel("measured_base", "量度移動 100%（基準）", spot + pole * 1.0, "up"),
        TargetLevel("measured_optimistic", "量度移動 120%（樂觀）", spot + pole * 1.2, "up"),
    ]


def channel_targets(df: pd.DataFrame, donchian_n: int) -> list[TargetLevel]:
    """通道目標：Bollinger 上軌/中軌（若已算）＋ Donchian N 日高。"""
    out: list[TargetLevel] = []
    spot = float(df["close"].iloc[-1])
    if "bb_upper" in df.columns and pd.notna(df["bb_upper"].iloc[-1]):
        out.append(TargetLevel("bb_upper", "布林上軌", float(df["bb_upper"].iloc[-1]), "up"))
    if "bb_mid" in df.columns and pd.notna(df["bb_mid"].iloc[-1]):
        mid = float(df["bb_mid"].iloc[-1])
        out.append(TargetLevel("bb_mid", "布林中軌（均值回歸）", mid, "up" if mid >= spot else "down"))
    w = max(2, min(donchian_n, len(df)))
    don_high = float(df["high"].iloc[-w:].max())
    out.append(TargetLevel("donchian_high", f"Donchian {donchian_n} 日高", don_high, "up"))
    return out


# --------------------------------------------------------------------------- #
# 主組裝
# --------------------------------------------------------------------------- #
def build_report(df: pd.DataFrame, symbol: str, spec: HorizonSpec) -> TargetReport | None:
    """組裝單一 horizon 的目標價報告。df 需含 close（high/low 用於技術價位）。"""
    if df is None or df.empty or "close" not in df.columns:
        return None
    spot = float(df["close"].iloc[-1])
    if not (spot > 0):
        return None

    h = spec.bars
    mu, sigma = gbm_params(df["close"], ret_lookback=spec.ret_lookback, zero_drift=spec.zero_drift)
    drift = (mu - 0.5 * sigma ** 2) * h
    vt = sigma * math.sqrt(h)
    median = spot * math.exp(drift)
    mean = spot * math.exp(mu * h)
    low70, high70 = spot * math.exp(drift - _Z70 * vt), spot * math.exp(drift + _Z70 * vt)
    low90, high90 = spot * math.exp(drift - _Z90 * vt), spot * math.exp(drift + _Z90 * vt)

    levels: list[TargetLevel] = []
    levels += pivot_points(df, spec.pivot_window)
    levels += fib_extensions(df, spec.fib_lookback)
    levels += measured_move(df, spec.pole_window)
    levels += channel_targets(df, spec.donchian_n)

    # 替每條技術目標價算達成機率
    for lv in levels:
        lv.prob_reach = prob_terminal(spot, lv.price, mu, sigma, h, lv.direction)

    # 彙整上檔三檔：保守＝最近的上檔目標、樂觀＝最遠者（含統計 90% 上界）、基準＝統計中位
    ups = sorted(lv.price for lv in levels if lv.direction == "up" and lv.price > spot)
    conservative = ups[0] if ups else high70
    optimistic = max(ups + [high90]) if ups else high90
    base = median

    return TargetReport(
        symbol=symbol, horizon_label=spec.label, horizon_bars=h, spot=spot,
        median=median, mean=mean, low70=low70, high70=high70, low90=low90, high90=high90,
        mu=mu, sigma=sigma, zero_drift=spec.zero_drift, levels=levels,
        conservative=conservative, base=base, optimistic=optimistic,
    )


def plain_summary(rep: TargetReport) -> str:
    """把整份報告濃縮成一句白話結論（簡易/進階模式都放在最上方）。"""
    def _chg(v: float) -> str:
        return f"{v:,.2f}（{v / rep.spot - 1:+.1%}）"

    p = prob_terminal(rep.spot, rep.conservative, rep.mu, rep.sigma, rep.horizon_bars, "up")
    pct = f"、達成機率約 {p * 100:.0f}%" if p is not None else ""
    return (
        f"**{rep.horizon_label}（未來 {rep.horizon_bars} 根 K 棒）**："
        f"第一目標約 {_chg(rep.conservative)}（最近技術關卡{pct}）；"
        f"順的話樂觀上看 {_chg(rep.optimistic)}；中位參考 {_chg(rep.base)}。"
        f"70% 機率落在 **{rep.low70:,.2f}–{rep.high70:,.2f}**。"
    )
