from dataclasses import dataclass
import trio


@dataclass
class Nursery:
    """Custom Nursery class to manage background tasks"""

    nursery: trio.Nursery
