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
class Publisher:
    name: str


@dataclass
class Attributes:
    prefix: str = None
    creators: List[Creator] = None
    titles: List[Title] = None
    publisher: Publisher = None
    publicationYear: int = None
    url: str = None
    types: Types = None
    # If None will create as "DRAFT"
    event: str = None


@dataclass
class Data:
    attributes: Attributes
    type: str = "dois"


@dataclass
class DOIPayload:
    data: Data
