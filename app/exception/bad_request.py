from dataclasses import dataclass
from typing import List, Optional
import dataclasses
import json


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


@dataclass
class ErrorDetails:
    code: str
    field: Optional[str]


class BadRequestException(Exception):
    def __init__(self, errors: List[ErrorDetails]):
        self.errors = errors
