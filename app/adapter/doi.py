from app.model.doi import (
    DOI as DOIModel, 
    Mode as ModeModel, 
    State as StateModel,
    Event as EventModel,
)
from app.model.db.doi import DOI as DOIDb
from app.gateway.doi.resource import (
    DOIPayload,
    Data as DOIPayloadData,
    Attributes as DOIPayloadAttributes,
    Creator as DOIPayloadCreator,
    Title as DOIPayloadTitle,
    Types as DOIPayloadTypes,
)


def database_to_model(doi: DOIDb) -> DOIModel:
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
        title=titles[0].get("title") if titles else None,
        creators=creators[0].get("name") if creators else None,
        publisher=publisher,
        publication_year=publication_year,
        resource_type=resource_type,
        url=doi.url,
        mode=ModeModel[doi.mode],
        state=StateModel[doi.state],
        provider_response=doi.doi,
    )


def model_to_payload(repository: str, doi: DOIModel) -> DOIPayload:
    return DOIPayload(
        data=DOIPayloadData(
            attributes=DOIPayloadAttributes(
                prefix=repository,
                creators=[
                    DOIPayloadCreator(name=creator.name) for creator in doi.creators
                ],
                titles=[DOIPayloadTitle(title=doi.title.title)],
                publisher=doi.publisher.publisher,
                publicationYear=doi.publication_year,
                url=doi.url,
                types=DOIPayloadTypes(resourceTypeGeneral=doi.resource_type),
            )
        )
    )

def database_to_payload(doi: DOIDb) -> DOIPayload:
    doi_data = doi.doi if doi.doi else {}
    data = doi_data.get("data", {})
    attributes = data.get("attributes", {})
    titles = attributes.get("titles", [{}])
    creators = attributes.get("creators", [{}])
    publisher = attributes.get("publisher", {})
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
                publisher=publisher,
                publicationYear=publication_year,
                url=doi.url,
                types=DOIPayloadTypes(resourceTypeGeneral=resource_type),
            )
        )
    )
    

def change_state_to_payload(doi: DOIDb, event: EventModel) -> DOIPayload:
    payload: DOIPayload = database_to_payload(doi)
    payload.data.attributes.event = event.name

    return payload

def model_to_database(doi: DOIModel) -> DOIDb:
    return DOIDb(
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