from dataclasses import dataclass
from typing import Optional

@dataclass
class TusResult:
    status_code: int
    body_msg: str
    reject_upload: Optional[bool] = None
