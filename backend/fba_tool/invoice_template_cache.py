"""进程内发票模板缓存：避免 Step 4.5 导出时重复上传整份 xlsx。"""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Optional

from settings import INVOICE_TEMPLATE_CACHE_MAX_ENTRIES

_MAX_ENTRIES = INVOICE_TEMPLATE_CACHE_MAX_ENTRIES
_cache: OrderedDict[str, bytes] = OrderedDict()


def hash_template(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_template(data: bytes) -> str:
    key = hash_template(data)
    _cache[key] = data
    _cache.move_to_end(key)
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)
    return key


def get_template(template_hash: str) -> Optional[bytes]:
    data = _cache.get(template_hash)
    if data is not None:
        _cache.move_to_end(template_hash)
    return data
