"""主流程：掃描 watchlist，對每個標的產生最新訊號並透過 Notifier 輸出。

執行：
    python scanner.py                 # 掃所有標的，印出當前訊號
    python scanner.py --only-signals  # 只印有 buy/sell 的標的

可由 Windows 工作排程器 / cron 定時呼叫。
"""
from __future__ import annotations

import sys

from core import load_config
from core import latest_signal
from notify.base import get_notifier


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    only_signals = "--only-signals" in argv

    cfg = load_config()
    notifier = get_notifier("console")
    watchlist = cfg.get("watchlist", [])

    print(f"掃描 {len(watchlist)} 檔標的…\n")
    for item in watchlist:
        symbol, market = item["symbol"], item["market"]
        name = item.get("name", symbol)
        try:
            sig = latest_signal(symbol, market, cfg)
        except Exception as e:  # 單一標的失敗不影響其他
            print(f"⚠ {name}（{symbol}）分析失敗：{e}")
            print("-" * 40)
            continue

        if sig is None:
            print(f"⚠ {name}（{symbol}）：抓不到資料")
            print("-" * 40)
            continue

        if only_signals and sig.action == "hold":
            continue

        print(f"【{name}】{sig.timestamp.date()}")
        notifier.send_signal(sig)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
