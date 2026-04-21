from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, BigInteger
from sqlalchemy.sql import func
from app.core.database import Base
import enum

class DataSource(str, enum.Enum):
    manual = "manual"
    ftp = "ftp"

class StorageType(str, enum.Enum):
    local = "local"
    ftp = "ftp"
    s3 = "s3"
    webdav = "webdav"

class ProcessStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    failed = "failed"

class Lot(Base):
    __tablename__ = "lots"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    product_name = Column(String, index=True)
    lot_id = Column(String, index=True)
    wafer_id = Column(String)
    program = Column(String)
    test_machine = Column(String)
    handler = Column(String)
    data_type = Column(String)        # CP / FT
    test_stage = Column(String)
    station_count = Column(Integer)
    die_count = Column(Integer)
    pass_count = Column(Integer)
    fail_count = Column(Integer)
    yield_rate = Column(Float)
    original_die_count = Column(Integer)
    original_pass_count = Column(Integer)
    original_fail_count = Column(Integer)
    original_yield_rate = Column(Float)
    test_date = Column(DateTime)
    upload_date = Column(DateTime, server_default=func.now())
    finish_date = Column(DateTime)

    # 文件存储
    data_source = Column(Enum(DataSource), default=DataSource.manual)
    storage_type = Column(Enum(StorageType), default=StorageType.local)
    storage_path = Column(String)
    file_size = Column(BigInteger)
    is_transferred = Column(Integer, default=0)
    local_expires_at = Column(DateTime)

    # 测试项数量
    item_count = Column(Integer, default=0)

    # 处理状态
    status = Column(Enum(ProcessStatus), default=ProcessStatus.pending)
    parquet_path = Column(String)

    # 关联
    user_id = Column(Integer, index=True)