"""Per-business third-party credentials, encrypted at rest."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config, market_research
from ..deps import owned_business

router = APIRouter(prefix="/api/businesses/{business_id}/integrations", tags=["integrations"])


class BraveSearchRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)


@router.get("/brave-search")
def brave_status(business: dict = Depends(owned_business)) -> dict:
    return market_research.brave_key_status(config.DB_PATH, business["id"])


@router.put("/brave-search")
def save_brave_key(payload: BraveSearchRequest, business: dict = Depends(owned_business)) -> dict:
    try:
        market_research.save_brave_key(config.DB_PATH, business["id"], payload.api_key)
    except market_research.MarketResearchError as error:
        raise HTTPException(503, str(error))
    return market_research.brave_key_status(config.DB_PATH, business["id"])


@router.delete("/brave-search")
def remove_brave_key(business: dict = Depends(owned_business)) -> dict:
    market_research.delete_brave_key(config.DB_PATH, business["id"])
    return {"configured": False}
