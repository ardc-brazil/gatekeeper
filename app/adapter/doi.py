from app.model.doi import (
    DOI as DOIModel,
    Event as EventModel,
    State as StateModel,
    Mode as ModeModel,
    Creator as DOICreator,
    Title as DOITitle,
    Publisher as DOIPublisher,
)
from app.model.db.doi import DOI as DOIDBModel
from app.gateway.doi.resource import (
    DOIPayload,
    Data as DOIPayloadData,
    Attributes as DOIPayloadAttributes,
    Creator as DOIPayloadCreator,
    Title as DOIPayloadTitle,
    Types as DOIPayloadTypes,
    Publisher as DOIPayloadPublisher,
)


def database_to_model(doi: DOIDBModel) -> DOIModel:
    doi_data = doi.doi if doi.doi else {}
    data = doi_data.get("data", {})
    attributes = data.get("attributes", {})
    titles = attributes.get("titles", [{}])
    creators = attributes.get("creators", [{}])
    publisher = attributes.get("publisher", {})
    publication_year = attributes.get("published", {})
    types = attributes.get("types", {})
    resource_type = types.get("resourceTypeGeneral", {})

    return DOIModel(
        identifier=doi.identifier,
        title=DOITitle(title=titles[0].get("title")) if titles else None,
        creators=[DOICreator(name=creator.get("name")) for creator in creators],
        publisher=DOIPublisher(publisher=publisher),
        publication_year=publication_year,
        resource_type=resource_type,
        url=doi.url,
        mode=ModeModel[doi.mode],
        state=StateModel[doi.state],
        provider_response=doi.doi,
    )


def model_to_payload(repository: str, doi: DOIModel) -> DOIPayload:
    creators = (
        [DOIPayloadCreator(name=creator.name) for creator in doi.creators]
        if doi.creators
        else []
    )
    titles = [DOIPayloadTitle(title=doi.title.title)] if doi.title else []

    resource_type = (
        DOIPayloadTypes(resourceTypeGeneral=doi.resource_type)
        if doi.resource_type
        else None
    )

    publisher = DOIPayloadPublisher(name=doi.publisher.publisher) if doi.publisher else None

    return DOIPayload(
        data=DOIPayloadData(
            attributes=DOIPayloadAttributes(
                prefix=repository,
                creators=creators,
                titles=titles,
                publisher=publisher,
                publicationYear=doi.publication_year,
                url=doi.url,
                types=resource_type,
            )
        )
    )


def database_to_payload(doi: DOIDBModel) -> DOIPayload:
    doi_data = doi.doi if doi.doi else {}
    data = doi_data.get("data", {})
    attributes = data.get("attributes", {})
    titles = attributes.get("titles", [{}])
    creators = attributes.get("creators", [{}])
    publisher = attributes.get("publisher", "")
    publication_year = attributes.get("published", {})
    types = attributes.get("types", {})
    resource_type = types.get("resourceTypeGeneral", {})

    return DOIPayload(
        data=DOIPayloadData(
            attributes=DOIPayloadAttributes(
                prefix=doi.prefix,
                creators=[
                    DOIPayloadCreator(name=creator.get("name")) for creator in creators
                ],
                titles=[DOIPayloadTitle(title=title.get("title")) for title in titles],
                publisher=DOIPayloadPublisher(name=publisher),
                publicationYear=publication_year,
                url=doi.url,
                types=DOIPayloadTypes(resourceTypeGeneral=resource_type),
            )
        )
    )


def change_state_to_payload(doi: DOIDBModel, event: EventModel) -> DOIPayload:
    payload: DOIPayload = database_to_payload(doi)
    payload.data.attributes.event = event.name.lower()

    return payload


def model_to_database(doi: DOIModel) -> DOIDBModel:
    return DOIDBModel(
        id=doi.id,
        identifier=doi.identifier,
        doi=doi.provider_response,
        url=doi.url,
        mode=doi.mode.name,
        state=doi.state.name,
        prefix=doi.identifier.split("/")[0],
        suffix=doi.identifier.split("/")[1],
        version_id=doi.dataset_version_id,
        created_by=doi.created_by,
    )
