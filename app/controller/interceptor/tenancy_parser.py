from fastapi import Depends
from fastapi.security import APIKeyHeader

tenancies = APIKeyHeader(
    name="X-Datamap-Tenancies", auto_error=False, scheme_name="X-Datamap-Tenancies"
)

async def parse_tenancy_header(tenancies: str = Depends(tenancies)) -> list[str]:
    if not tenancies:
        return []
    
    return [tenancy.strip() for tenancy in tenancies.split(";")]
