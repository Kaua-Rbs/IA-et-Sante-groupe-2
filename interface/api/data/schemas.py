from pydantic import BaseModel, Field
from datetime import date
from typing import Literal

class ImportResponse(BaseModel):
    filename: str = Field(..., description="Name of the imported file", examples=["donees_bloc.csv"])
    rows_processed: int = Field(..., description="Total number of rows analyzed", examples=[14649])
    success_count: int = Field(..., description="Number of items successfully imported", examples=[14640])
    error_count: int = Field(..., description="Number of items that failed to import", examples=[9])
    message: str = Field(..., description="Summary message of the operation", examples=["Import completed successfully with minor errors."])

class ExportRequest(BaseModel):
    start_date: date = Field(..., description="Start date for the schedule export", examples=["2026-10-01"])
    end_date: date = Field(..., description="End date for the schedule export", examples=["2026-10-31"])
    format: Literal["csv", "pdf", "json"] = Field("csv", description="Desired export format")
