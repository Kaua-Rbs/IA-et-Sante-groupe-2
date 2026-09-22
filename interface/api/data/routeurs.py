from fastapi import APIRouter, UploadFile, File, Depends
from fastapi.responses import FileResponse
from .schemas import ImportResponse, ExportRequest

router = APIRouter(
    prefix="/data",
    tags=["Import / Export"],
)

@router.post("/import_dataset", response_model=ImportResponse)
async def import_dataset(file: UploadFile = File(...)):
    """Upload d'un fichier CSV/Excel pour peupler la base de données (ex: historique)."""
    pass

@router.post("/export_schedule")
async def export_schedule(request: ExportRequest):
    """Exporte le planning au format demandé."""
    pass
