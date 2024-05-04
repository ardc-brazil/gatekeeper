from fastapi import APIRouter
from fastapi.responses import JSONResponse


router = APIRouter(
    prefix="/health-check",
    tags=["health-check"]
)

@router.get("/")
async def health_check():
    return JSONResponse(content={"status": "online"})
