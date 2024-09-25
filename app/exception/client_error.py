from dataclasses import dataclass
from typing import List, Optional
import dataclasses, json

class EnhancedJSONEncoder(json.JSONEncoder):
        def default(self, o):
            if dataclasses.is_dataclass(o):
                return dataclasses.asdict(o)
            return super().default(o)
@dataclass
class ErrorDetails:
    code: str
    field: Optional[str]

@dataclass
class ClientErrors:
    errors: List[ErrorDetails]

class ClientErrorException(Exception):
    def __init__(self, code: int, errors: ClientErrors ):
        self.code = code
        self.errors = errors
