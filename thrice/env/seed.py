"""OTLP seed helpers.

`stamp_now` exists because of the G2 correction: Jaeger's /api/traces applies
a default lookback window, so spans timestamped in the past are stored but
invisible. A plan therefore carries RELATIVE offsets and the runner stamps
them at seed time, which also keeps a plan reproducible next month.
"""

from __future__ import annotations

import copy
import time
from typing import Any


def stamp_now(payload: dict[str, Any]) -> dict[str, Any]:
    """Rewrite `startOffsetMs`/`endOffsetMs` on each span into absolute nanos.

    Offsets are milliseconds BEFORE now, so `startOffsetMs: 2000` means the
    span started two seconds ago. Absolute timestamps in a plan are left alone.
    """
    out = copy.deepcopy(payload)
    now_ns = int(time.time() * 1e9)
    for rs in out.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                if "startOffsetMs" in span:
                    span["startTimeUnixNano"] = str(now_ns - int(span.pop("startOffsetMs")) * 1_000_000)
                if "endOffsetMs" in span:
                    span["endTimeUnixNano"] = str(now_ns - int(span.pop("endOffsetMs")) * 1_000_000)
    return out
