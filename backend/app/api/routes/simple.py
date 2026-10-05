"""Plain-language view for everyday users."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.services.simple_view import simple_view

router = APIRouter(prefix="/simple", tags=["simple"], dependencies=[Depends(get_current_user)])


@router.get("")
def simple(refresh: bool = False, db: Session = Depends(get_db)) -> dict:
    from app.services.live_market import maybe_refresh

    maybe_refresh(db)
    return simple_view(db, refresh=refresh)
