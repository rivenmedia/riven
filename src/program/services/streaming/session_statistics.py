import time
from dataclasses import dataclass, field


@dataclass
class SessionStatistics:
    """Statistics about the current streaming session."""

    bytes_transferred: int = 0
    total_session_connections: int = 0
    started_at: float = field(default_factory=time.monotonic)
