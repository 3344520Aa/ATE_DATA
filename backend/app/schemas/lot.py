from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class LotResponse(BaseModel):
    id: int
    filename: str
    product_name: Optional[str]
    lot_id: Optional[str]
    wafer_id: Optional[str]
    program: Optional[str]
    test_machine: Optional[str]
    data_type: Optional[str]
    test_stage: Optional[str]
    station_count: Optional[int]
    die_count: Optional[int]
    pass_count: Optional[int]
    fail_count: Optional[int]
    yield_rate: Optional[float]
    status: Optional[str]
    file_size: Optional[int]
    test_date: Optional[datetime]
    upload_date: Optional[datetime]
    finish_date: Optional[datetime]
    data_source: Optional[str]
    item_count: Optional[int]

    class Config:
        from_attributes = True

class LotListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[LotResponse]