"""
全局停止标志：用于中断全部回复和自由讨论。
"""
from typing import Dict
import threading

_stop_flags: Dict[int, bool] = {}
_lock = threading.Lock()


def set_stop(conversation_id: int, value: bool = True):
    with _lock:
        _stop_flags[conversation_id] = value


def is_stopped(conversation_id: int) -> bool:
    with _lock:
        return _stop_flags.get(conversation_id, False)


def clear_stop(conversation_id: int):
    with _lock:
        _stop_flags.pop(conversation_id, None)
