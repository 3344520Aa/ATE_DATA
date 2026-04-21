import os
import shutil
import zipfile
import io
from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel
from app.core.database import get_db
from app.core.config import settings
from app.models.lot import Lot
from app.schemas.lot import LotResponse, LotListResponse
from datetime import datetime, timedelta, timezone
from app.services.parsers import parse_file
from app.models.bin_summary import BinSummary
from app.models.test_item import TestItem

router = APIRouter(prefix="/lots", tags=["lots"])

UPLOAD_DIR = os.path.expanduser(settings.UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    results = []
    for file in files:
        try:
            result = await _process_upload(file, db, background_tasks)
            results.append(result)
        except Exception as e:
            results.append({"filename": file.filename, "status": "failed", "error": str(e)})
    return {"results": results}


async def _process_upload(file: UploadFile, db: Session, background_tasks: BackgroundTasks):
    filename = file.filename
    ext = os.path.splitext(filename)[-1].lower()
    base_name = os.path.splitext(filename)[0]

    # 重复文件名处理：自动追加数字
    save_path = os.path.join(UPLOAD_DIR, filename)
    counter = 1
    while os.path.exists(save_path):
        new_filename = f"{base_name}_{counter}{ext}"
        save_path = os.path.join(UPLOAD_DIR, new_filename)
        counter += 1
    filename = os.path.basename(save_path)

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    file_size = len(content)

    # 如果是zip，解压找csv
    csv_path = save_path
    if ext == '.zip':
        extract_dir = os.path.join(UPLOAD_DIR, os.path.splitext(filename)[0])
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(save_path, 'r') as z:
            z.extractall(extract_dir)
        # 找第一个csv文件
        csv_files = [
            os.path.join(extract_dir, f)
            for f in os.listdir(extract_dir)
            if f.endswith('.csv')
        ]
        if not csv_files:
            raise HTTPException(status_code=400, detail="ZIP中未找到CSV文件")
        csv_path = csv_files[0]

    # 快速识别tester类型，提取基本元数据
    from app.services.parsers.detector import detect_tester
    tester = detect_tester(csv_path)

    # 创建LOT记录（先存pending状态）
    lot = Lot(
        filename=filename,
        storage_path=save_path,
        file_size=file_size,
        status='pending',
        data_source='manual',
        storage_type='local',
        local_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        upload_date=datetime.now(timezone.utc),
        test_machine=tester,
    )

    # 快速解析表头获取基本信息
    try:
        meta = _quick_parse_meta(csv_path, tester)
        lot.program = meta.get('program')
        lot.lot_id = meta.get('lot_id')
        lot.wafer_id = meta.get('wafer_id')
        lot.handler = meta.get('handler')
        lot.data_type = meta.get('test_stage')
        # test_date 已由 parser 统一处理为标准字符串（YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD）
        td_str = meta.get('test_date')
        if td_str:
            try:
                if len(td_str) == 19:
                    lot.test_date = datetime.strptime(td_str, '%Y-%m-%d %H:%M:%S')
                elif len(td_str) == 10:
                    lot.test_date = datetime.strptime(td_str, '%Y-%m-%d')
            except Exception:
                pass
    except Exception:
        pass

    db.add(lot)
    db.commit()
    db.refresh(lot)

    # 触发异步解析任务
    background_tasks.add_task(_parse_and_save_bg, lot.id, csv_path)

    return {
        "filename": filename,
        "status": lot.status,
        "lot_id": lot.id
    }


def _parse_and_save_bg(lot_id: int, csv_path: str):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        _parse_and_save(lot_id, csv_path, db)
    except Exception as e:
        print(f"[_parse_and_save_bg] error: {e}")
    finally:
        db.close()

def _quick_parse_meta(csv_path: str, tester: str) -> dict:
    """快速读取表头元数据，不解析数据部分"""
    from app.services.parsers.acco_parser import parse_acco

    # 所有格式统一走 parse_acco，它能处理 ETS364/LBS/T2K/UNKNOWN 的表头
    result = parse_acco(csv_path, tester)

    if result.error:
        return {}

    return {
        'program': result.program,
        'lot_id': result.lot_id,
        'wafer_id': result.wafer_id,
        'handler': result.handler,
        'test_stage': result.test_stage,
        'beginning_time': result.beginning_time,
        'ending_time': result.ending_time,
        'test_date': result.test_date,   # 已标准化的测试日期字符串
    }

def _parse_and_save(lot_id: int, csv_path: str, db: Session):
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        return

    lot.status = 'processing'
    db.commit()

    try:
        result = parse_file(csv_path)
        print(f"[parse] 解析完成 error={result.error}")

        if result.error:
            raise Exception(result.error)

        # 保存Parquet
        parquet_dir = os.path.join(UPLOAD_DIR, 'parquet')
        os.makedirs(parquet_dir, exist_ok=True)
        parquet_path = os.path.join(parquet_dir, f"lot_{lot_id}.parquet")
        result.data.to_parquet(parquet_path, index=False)
        print(f"[parse] Parquet保存完成 {parquet_path}")

        lot.parquet_path = parquet_path

        # BIN 1/2 为 PASS，其他为 FAIL（业务规则，不依赖表头）
        PASS_BINS = [1, 2]

        lot.station_count = int(result.data['SITE_NUM'].nunique())

        if lot.program:
            from app.models.product_mapping import ProductMapping
            from app.api.routes.products import extract_program_prefix
            prefix = extract_program_prefix(lot.program)
            if prefix:
                mapping = db.query(ProductMapping).filter(
                    ProductMapping.program_prefix == prefix
                ).first()
                if mapping:
                    lot.product_name = mapping.product_name

        from app.services.stats import save_stats_to_db
        save_stats_to_db(lot, result, db, PASS_BINS)
        print(f"[parse] 统计计算完成")

        lot.status = 'processed'
        lot.finish_date = datetime.now(timezone.utc)
        db.commit()
        print(f"[parse] 全部完成 lot_id={lot_id}")

    except Exception as e:
        import traceback
        print(f"[parse] 错误: {e}")
        traceback.print_exc()
        lot.status = 'failed'
        db.commit()



@router.get("", response_model=LotListResponse)
def get_lots(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    product_name: Optional[str] = None,
    lot_id: Optional[str] = None,
    status: Optional[str] = None,
    data_type: Optional[str] = None,
):
    query = db.query(Lot)
    if product_name:
        query = query.filter(Lot.product_name.ilike(f"%{product_name}%"))
    if lot_id:
        query = query.filter(Lot.lot_id.ilike(f"%{lot_id}%"))
    if status:
        query = query.filter(Lot.status == status)
    if data_type:
        query = query.filter(Lot.data_type == data_type)

    total = query.count()
    items = query.order_by(desc(Lot.upload_date)).offset(
        (page-1)*page_size
    ).limit(page_size).all()

    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size
    }


@router.delete("")
def delete_lots(data: dict = Body(...), db: Session = Depends(get_db)):
    import shutil
    ids = data.get("ids", [])
    deleted_count = 0
    for lot_id in ids:
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if lot:
            # 1. 删除关联的统计数据（外键约束）
            db.query(BinSummary).filter(BinSummary.lot_id == lot_id).delete()
            db.query(TestItem).filter(TestItem.lot_id == lot_id).delete()

            # 2. 删除物理文件
            if lot.storage_path and os.path.exists(lot.storage_path):
                try:
                    if os.path.isdir(lot.storage_path):
                        shutil.rmtree(lot.storage_path)
                    else:
                        os.remove(lot.storage_path)
                except Exception as e:
                    print(f"Error deleting storage_path {lot.storage_path}: {e}")
            
            if lot.parquet_path and os.path.exists(lot.parquet_path):
                try:
                    os.remove(lot.parquet_path)
                except Exception as e:
                    print(f"Error deleting parquet_path {lot.parquet_path}: {e}")

            # 3. 删除主记录
            db.delete(lot)
            deleted_count += 1
    
    db.commit()
    return {"deleted": deleted_count}


class MergeRequest(BaseModel):
    ids: List[int]
    new_name: str
    new_lot_id: str = ""
    new_wafer_id: str = ""

@router.post("/merge")
def merge_lots(data: MergeRequest, db: Session = Depends(get_db)):
    """
    合并多个LOT：
    1. 校验产品名一致
    2. 校验参数名完全一致
    3. 按 test_date 时序合并 parquet，坐标相同保留最后一次
    4. 重新计算统计，生成新 Lot 记录
    """
    import pandas as pd
    from datetime import timezone

    if len(data.ids) < 2:
        raise HTTPException(status_code=400, detail="至少选择2条记录")

    lots = db.query(Lot).filter(Lot.id.in_(data.ids)).all()
    if len(lots) != len(data.ids):
        raise HTTPException(status_code=404, detail="部分LOT不存在")

    # 按 test_date 排序（None 排最后）
    lots.sort(key=lambda l: l.test_date or datetime.min)

    # 1. 校验产品名一致
    product_names = set(l.product_name for l in lots if l.product_name)
    if len(product_names) > 1:
        raise HTTPException(status_code=400, detail=f"产品名不一致，无法合并: {product_names}")

    # 2. 读取所有 parquet，校验参数名
    dfs = []
    param_names_list = []
    for lot in lots:
        if not lot.parquet_path or not os.path.exists(lot.parquet_path):
            raise HTTPException(status_code=400, detail=f"LOT {lot.id} 数据文件不存在，无法合并")
        df = pd.read_parquet(lot.parquet_path)
        # 非测试参数列
        meta_cols = {'SITE_NUM', 'SOFT_BIN', 'HARD_BIN', 'X_COORD', 'Y_COORD', 'DIE_ID', 'PART_ID'}
        param_cols = [c for c in df.columns if c not in meta_cols]
        param_names_list.append(set(param_cols))
        dfs.append(df)

    # 校验参数名一一对应
    ref_params = param_names_list[0]
    for i, pset in enumerate(param_names_list[1:], 1):
        if pset != ref_params:
            diff = ref_params.symmetric_difference(pset)
            raise HTTPException(status_code=400, detail=f"参数名不一致，差异项: {diff}")

    # 3. 按时序拼接，坐标去重保留最后一次
    merged_df = pd.concat(dfs, ignore_index=True)

    has_coords = (
        'X_COORD' in merged_df.columns and
        'Y_COORD' in merged_df.columns and
        merged_df['X_COORD'].notna().any() and
        ((merged_df['X_COORD'] != 0) | (merged_df['Y_COORD'] != 0)).any()
    )

    if has_coords:
        merged_df = merged_df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')

    # 4. 保存新 parquet
    parquet_dir = os.path.join(UPLOAD_DIR, 'parquet')
    os.makedirs(parquet_dir, exist_ok=True)

    # 先建 Lot 记录拿到 id
    ref_lot = lots[0]
    new_lot = Lot(
        filename=data.new_name,
        product_name=ref_lot.product_name,
        lot_id=data.new_lot_id or ref_lot.lot_id,
        wafer_id=data.new_wafer_id or ref_lot.wafer_id,
        program=ref_lot.program,
        test_machine=ref_lot.test_machine,
        handler=ref_lot.handler,
        data_type=ref_lot.data_type,
        test_date=ref_lot.test_date,
        status='processing',
        data_source='manual',
        storage_type='local',
        upload_date=datetime.now(timezone.utc),
    )
    db.add(new_lot)
    db.commit()
    db.refresh(new_lot)

    parquet_path = os.path.join(parquet_dir, f"lot_{new_lot.id}.parquet")
    merged_df.to_parquet(parquet_path, index=False)
    new_lot.parquet_path = parquet_path
    db.commit()

    # 5. 重新计算统计
    try:
        from app.services.parsers.base import ParsedData
        from app.services.stats import save_stats_to_db

        # 从第一个 lot 的 TestItem 重建 param 元数据
        ref_items = db.query(TestItem).filter(
            TestItem.lot_id == ref_lot.id,
            TestItem.site == 0
        ).order_by(TestItem.item_number).all()

        meta_cols_set = {'SITE_NUM', 'SOFT_BIN', 'HARD_BIN', 'X_COORD', 'Y_COORD', 'DIE_ID', 'PART_ID'}
        param_names = [it.item_name for it in ref_items]
        param_ll = {it.item_name: it.lower_limit for it in ref_items}
        param_ul = {it.item_name: it.upper_limit for it in ref_items}
        param_units = {it.item_name: it.unit for it in ref_items}

        # 从第一个 lot 的 BinSummary 重建 bin_definitions
        bin_rows = db.query(BinSummary).filter(
            BinSummary.lot_id == ref_lot.id,
            BinSummary.site == 0,
            BinSummary.data_range == 'final'
        ).all()
        bin_definitions = {b.bin_number: {'name': b.bin_name} for b in bin_rows}

        parsed = ParsedData(
            data=merged_df,
            param_names=param_names,
            param_ll=param_ll,
            param_ul=param_ul,
            param_units=param_units,
            bin_definitions=bin_definitions,
        )

        PASS_BINS = [1, 2]
        save_stats_to_db(new_lot, parsed, db, PASS_BINS)

        new_lot.status = 'processed'
        new_lot.finish_date = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
        new_lot.status = 'failed'
        db.commit()
        raise HTTPException(status_code=500, detail=f"合并统计失败: {e}")

    return {"id": new_lot.id, "filename": new_lot.filename, "status": new_lot.status}


class DownloadRequest(BaseModel):
    ids: List[int]


@router.post("/download")
def download_lots(data: DownloadRequest, db: Session = Depends(get_db)):
    """
    下载选中LOT的原始数据文件，打包为ZIP返回。
    支持单条或多条同时下载。
    """
    ids = data.ids
    if not ids:
        raise HTTPException(status_code=400, detail="未选择任何记录")

    lots = db.query(Lot).filter(Lot.id.in_(ids)).all()
    if not lots:
        raise HTTPException(status_code=404, detail="选中的记录不存在")

    # 准备ZIP文件（内存流）
    zip_buffer = io.BytesIO()
    added_files = []
    missing_files = []

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for lot in lots:
            file_path = lot.storage_path
            if not file_path or not os.path.exists(file_path):
                missing_files.append(lot.filename)
                continue

            # 使用原始文件名，若重名则加lot_id前缀区分
            arcname = lot.filename
            # 检查ZIP中是否已存在同名文件
            existing_names = [info.filename for info in zf.infolist()]
            if arcname in existing_names:
                arcname = f"lot_{lot.id}_{arcname}"

            zf.write(file_path, arcname)
            added_files.append(arcname)

    if not added_files:
        raise HTTPException(status_code=404, detail="所有选中记录的文件均不存在或已丢失")

    zip_buffer.seek(0)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_filename = f"ATE_OriginalData_{timestamp}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    )