from dataclasses import dataclass
import enum
from typing import List


class Event(enum.Enum):
    PUBLISH = "publish"
    REGISTER = "register"


@dataclass
class Creator:
    # nameType = "Personal" or "Organizational"
    # givenName
    # familyName
    # nameIdentifier = https://orcid.org/0000-0002-1825-0097
    # nameIdentifierScheme = "ORCID"
    # nameIdentifierSchemeURI = "https://orcid.org"
    # affiliation: Affiliation = None
    name: str

@dataclass
class Afilliation:
    pass
    # name: str
    # affiliationIdentifier
    # affiliationIdentifierScheme
    # affiliationIdentifierSchemeURI

@dataclass
class Contributor:
    pass
    # name: str
    # nameType: = "Personal" or "Organizational"
    # givenName
    # familyName
    # affiliation: Affiliation = None
    # contributorType
    # nameIdentifier = https://orcid.org/0000-0002-1825-0097
    # nameIdentifierScheme = "ORCID"
    # nameIdentifierSchemeURI = "https://orcid.org"

@dataclass
class ResourceDate:
    pass
    # date: str
    # dateType: DateType
    # dateInformation: str

@dataclass
class RelatedIdentifier:
    pass
    # relatedIdentifierType = "DOI"
    # relationType = "IsNewVersionOf"
    # relatedIdentifier: str
    # resourceTypeGeneral = "Dataset"

@dataclass
class Right:
    pass
    # rights: str https://spdx.org/licenses/
    # rightsURI: str
    # rightsIdentifier: str
    # rightsIdentifierScheme: str
    # rightsIdentifierSchemeURI: str

@dataclass
class Description:
    pass
    # description: str = dataset description + provenance + temporal coverage
    # descriptionType: DescriptionType = "Abstract"

@dataclass
class GeoLocationPoint:
    pass
    # pointLongitude: float
    # pointLatitude: float

@dataclass
class GeoLocation:
    pass
    # geoLocationPlace: str
    # geoLocationPoint: GeoLocationPoint = None

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
    # When creating, if "event" is None will create DOI in "DRAFT" state
    event: str = None
    # contributors: List[Contributor] = None
    # dates: [ResourceDate] = None
    # relatedIdentifiers: [RelatedIdentifier] = None
    # sizes: List[str] = None # 10 files, 500 mb
    # formats: List[str] = None # extensions normalized
    # version: str = None
    # rightsList: List[Right] = None
    # descriptions: List[Description] = None
    # geoLocations: List[GeoLocation] = None

@dataclass
class Data:
    attributes: Attributes
    type: str = "dois"


@dataclass
class DOIPayload:
    data: Data
