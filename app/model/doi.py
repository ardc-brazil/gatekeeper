from dataclasses import dataclass, field
from datetime import datetime
import enum
from uuid import UUID


class State(enum.Enum):
    DRAFT = "draft"
    REGISTERED = "registered"
    FINDABLE = "findable"

class TitleType(enum.Enum):
    ALTERNATIVE_TITLE = "alternative-title"
    SUBTITLE = "subtitle"
    TRANSLATED_TITLE = "translated-title"
    OTHER = "other"

class Mode(enum.Enum):
    MANUAL = "manual"
    AUTO = "auto"

@dataclass
class Publisher:
    publisher: str
    publisher_identifier: str = None
    publisher_identifier_scheme: str = None
    scheme_uri: str = None

@dataclass
class Title:
    title: str
    type: TitleType = None

@dataclass
class NameIdentifier:
    name_identifier: str
    name_identifier_scheme: str
    scheme_uri: str

@dataclass
class Affiliation:
    affiliation: str
    affiliation_identifier: str = None
    affiliation_identifier_scheme: str = None
    scheme_uri: str = None

@dataclass
class Creator:
    name: str
    name_type: str = None
    given_name: str = None
    family_name: str = None
    affiliation: list[Affiliation] = field(default_factory=lambda: [])
    name_identifier: list[NameIdentifier] = field(default_factory=lambda: [])

@dataclass
class Identifier:
    identifier: str
    type: str = "DOI"

@dataclass
class DOI:
    identifier: Identifier
    title: Title
    other_titles: list[Title]
    creators: list[Creator]
    publication_year: int
    publisher: Publisher
    resource: str
    mode: Mode
    state: State = State.DRAFT
    resource_type: str = "Dataset"
    created_at: datetime = None
    updated_at: datetime = None
    created_by: UUID = None
    id: UUID = None
