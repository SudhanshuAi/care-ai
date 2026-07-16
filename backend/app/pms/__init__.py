"""PMS provider boundary.

`MockPmsAdapter` is the default durable integration used by the application.
Future vendor adapters implement the same protocol without changing booking
or retry logic.
"""

from app.pms.mock import MockPmsAdapter
from app.pms.protocol import PmsAdapter, PmsWritebackError, PmsWritebackResult

__all__ = [
    "MockPmsAdapter",
    "PmsAdapter",
    "PmsWritebackError",
    "PmsWritebackResult",
]
