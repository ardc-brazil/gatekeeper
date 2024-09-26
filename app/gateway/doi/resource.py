from dataclasses import dataclass
import enum
from typing import List

class Event(enum.Enum):
    PUBLISH = "publish"
    REGISTER = "register"

@dataclass
class Creator:
    name: str

@dataclass
class Title:
    title: str

@dataclass
class Types:
    resourceTypeGeneral: str = "Dataset"

@dataclass
class Attributes:
    prefix: str
    creators: List[Creator]
    titles: List[Title]
    publisher: str
    publicationYear: int
    url: str
    types: Types = Types()
    # If None will create as "DRAFT"
    event: str = None

@dataclass
class Data:
    attributes: Attributes
    type: str = "dois"

@dataclass
class DOIPayload:
    data: Data
