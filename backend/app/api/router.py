"""
AEGIS Main API Router

Autonomous Enterprise Global Intelligence System
Company: Honeydewnuts Nigerian Limited
"""

from fastapi import APIRouter

router = APIRouter()

# NOTE: upload_router is registered directly in main.py - it used to
# also be nested here, which registered every /upload/* route twice.

# ------------------------------------------------------------------
# Root API Endpoint
# ------------------------------------------------------------------

@router.get("/")
async def api_root():
    return {
        "application": "AEGIS",
        "description": "Autonomous Enterprise Global Intelligence System",
        "company": "Honeydewnuts Nigerian Limited",
        "version": "0.1.0",
        "status": "Running"
    }


# ------------------------------------------------------------------
# Health Check
# ------------------------------------------------------------------

@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "AEGIS Backend",
        "version": "0.1.0"
    }
