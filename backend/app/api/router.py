from fastapi import APIRouter

from app.api.routes import (
    admin,
    auth,
    backtests,
    fno_paper,
    health,
    journal,
    market,
    opportunities,
    portfolio,
    stocks,
    tax,
    tools,
    watch,
)

api_router = APIRouter()
for r in (health, auth, market, opportunities, stocks, tools, portfolio, journal, tax, watch, fno_paper, backtests,
          admin):
    api_router.include_router(r.router)
