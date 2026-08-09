"""Low-cardinality counters suitable for basic Prometheus scraping and alerts."""

import re
import time
from collections import Counter

METRIC_PART = re.compile(r"[^a-zA-Z0-9_]")


class Monitoring:
    """Track operational events without retaining user or message data."""

    def __init__(self) -> None:
        self.started_at = time.monotonic()
        self._counters: Counter[tuple[str, str]] = Counter()

    def increment(self, name: str, component: str = "bot") -> None:
        safe_name = METRIC_PART.sub("_", name)
        safe_component = METRIC_PART.sub("_", component)
        self._counters[(safe_name, safe_component)] += 1

    def value(self, name: str, component: str = "bot") -> int:
        return self._counters[(name, component)]

    def render(self) -> str:
        lines = [
            "# TYPE subtitle_bot_up gauge",
            "subtitle_bot_up 1",
            "# TYPE subtitle_bot_uptime_seconds gauge",
            f"subtitle_bot_uptime_seconds {max(0, int(time.monotonic() - self.started_at))}",
        ]
        declared: set[str] = set()
        for (name, component), value in sorted(self._counters.items()):
            if name not in declared:
                lines.append(f"# TYPE subtitle_bot_{name}_total counter")
                declared.add(name)
            lines.append(f'subtitle_bot_{name}_total{{component="{component}"}} {value}')
        return "\n".join(lines) + "\n"


monitoring = Monitoring()
