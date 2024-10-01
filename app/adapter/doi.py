from app.model.doi import DOI as DOIModel, Mode as ModeModel, State as StateModel
from app.model.db.doi import DOI as DOIDb
from app.gateway.doi.resource import DOIPayload, Data as DOIPayloadData, Attributes as DOIPayloadAttributes, Creator as DOIPayloadCreator, Title as DOIPayloadTitle, Types as DOIPayloadTypes

def database_to_model(doi: DOIDb) -> DOIModel:
    return DOIModel(
        identifier=doi.identifier,
        title=doi.doi['title'],
        creators=doi.doi['creators'],
        publisher=doi.doi['publisher'],
        publication_year=doi.doi['publication_year'],
        resource_type=doi.doi['resource_type'],
        url=doi.url,
        mode=ModeModel[doi.mode],
        state=StateModel[doi.state],
        provider_response=doi.doi,
    )

def model_to_payload(doi: DOIModel) -> DOIPayload:
        return DOIPayload(
            data=DOIPayloadData(
                attributes=DOIPayloadAttributes(
                    prefix=doi.identifier.split("/")[0],
                    creators=[DOIPayloadCreator(name=creator['name']) for creator in doi.creators],
                    titles=[DOIPayloadTitle(title=doi.title)],
                    publisher=doi.publisher,
                    publicationYear=doi.publication_year,
                    url=doi.url,
                    types=DOIPayloadTypes(resourceTypeGeneral=doi.resource_type),
                )
            )
        )