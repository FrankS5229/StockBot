"""通知介面（可插拔）。

v1 只提供介面 + ConsoleNotifier（印到終端）佔位。
之後選定 Discord Webhook / ntfy.sh / Email 後，新增對應子類別即可，
scanner 與儀表板都透過 Notifier 介面呼叫，不需改動。
"""
from __future__ import annotations

import abc

from strategy.base import Signal


class Notifier(abc.ABC):
    """通知器抽象基底。"""

    @abc.abstractmethod
    def send(self, text: str) -> None:
        """送出一則純文字訊息。"""
        raise NotImplementedError

    def send_signal(self, signal: Signal) -> None:
        """送出一個訊號（預設轉成白話文字）。"""
        self.send(signal.as_text())


class ConsoleNotifier(Notifier):
    """把訊息印到終端（v1 預設）。"""

    def send(self, text: str) -> None:
        print(text)
        print("-" * 40)


def get_notifier(name: str = "console") -> Notifier:
    """依名稱取得通知器。目前僅 console；之後可擴充。"""
    name = (name or "console").lower()
    if name == "console":
        return ConsoleNotifier()
    raise ValueError(f"尚未支援的通知管道：{name!r}（v1 僅 console）")
