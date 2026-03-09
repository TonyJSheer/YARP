import msgspec
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.services import document_service
from app.services.auth import get_current_account_id

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=None)
async def list_collections(
    account_id: str = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, object]]]:
    items = document_service.list_collections(account_id, db)
    return {"collections": [msgspec.to_builtins(item) for item in items]}
