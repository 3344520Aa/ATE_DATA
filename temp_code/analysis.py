import os
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List
from pydantic import BaseModel
import pandas as pd
import numpy as np
from app.core.database import get_db
from app.models.test_item import TestItem
from app.models.bin_summary import BinSummary
from app.models.lot import Lot

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/lot/{lot_id}/info")
def get_lot_info(lot_id: int, db: Session = Depends(get_db)):
    """获取LOT基本信息"""
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="LOT不存在")
    return {
        "id": lot.id,
        "filename": lot.filename,
        "program": lot.program,
        "lot_id": lot.lot_id,
        "wafer_id": lot.wafer_id,
        "test_machine": lot.test_machine,
        "handler": lot.handler,
        "data_type": lot.data_type,
        "station_count": lot.station_count,
        "die_count": lot.die_count,
        "pass_count": lot.pass_count,
        "fail_count": lot.fail_count,
        "yield_rate": lot.yield_rate,
        "test_date": lot.test_date,
        "upload_date": lot.upload_date,
    }


@router.get("/lot/{lot_id}/items")
def get_test_items(
    lot_id: int,
    db: Session = Depends(get_db),
    site: int = Query(0),
):
    """获取参数列表（用于参数详情页表格）"""
    items = db.query(TestItem).filter(
        and_(TestItem.lot_id == lot_id, TestItem.site == site)
    ).order_by(TestItem.item_number).all()

    return [
        {
            "id": item.id,
            "item_number": item.item_number,
            "item_name": item.item_name,
            "unit": item.unit,
            "lower_limit": item.lower_limit,
            "upper_limit": item.upper_limit,
            "exec_qty": item.exec_qty,
            "fail_count": item.fail_count,
            "fail_rate": item.fail_rate,
            "yield_rate": item.yield_rate,
            "mean": item.mean,
            "stdev": item.stdev,
            "min_val": item.min_val,
            "max_val": item.max_val,
            "cpu": item.cpu,
            "cpl": item.cpl,
            "cpk": item.cpk,
        }
        for item in items
    ]


@router.get("/lot/{lot_id}/top_fail")
def get_top_fail(
    lot_id: int,
    db: Session = Depends(get_db),
    top_n: int = Query(5),
):
    """获取Top Fail参数（用于右上角柱状图）"""
    # All Sites 的失效数据
    items = db.query(TestItem).filter(
        and_(
            TestItem.lot_id == lot_id,
            TestItem.site == 0,
            TestItem.fail_count > 0
        )
    ).order_by(TestItem.fail_count.desc()).limit(top_n).all()

    # 各Site的Top Fail
    sites = db.query(TestItem.site).filter(
        and_(TestItem.lot_id == lot_id, TestItem.site > 0)
    ).distinct().all()
    site_list = sorted([s[0] for s in sites])

    result = []
    for item in items:
        row = {
            "item_name": item.item_name,
            "fail_count": item.fail_count,
            "fail_rate": item.fail_rate,
            "sites": {}
        }
        # 查各Site的失效数
        for site in site_list:
            site_item = db.query(TestItem).filter(
                and_(
                    TestItem.lot_id == lot_id,
                    TestItem.item_name == item.item_name,
                    TestItem.site == site
                )
            ).first()
            if site_item:
                row["sites"][f"site{site}"] = site_item.fail_count
        result.append(row)

    return {"items": result, "sites": site_list}

@router.get("/lot/{lot_id}/bin_definitions")
def get_bin_definitions(lot_id: int, db: Session = Depends(get_db)):
    """获取Bin定义和Pass Bins"""
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="LOT不存在")

    bins = db.query(BinSummary).filter(
        and_(BinSummary.lot_id == lot_id, BinSummary.site == 0)
    ).all()

    # 读取Parquet获取bin定义
    if not lot.parquet_path:
        return {"pass_bins": [1, 2]}

    import pandas as pd
    try:
        df = pd.read_parquet(lot.parquet_path)
        all_bins = df['SOFT_BIN'].dropna().unique().astype(int).tolist()
    except Exception:
        all_bins = []

    # 暂时用bin汇总里数量最多的bin作为pass bin判断依据
    # 实际应从parsed.bin_definitions里读hard_bin=1的
    pass_bins = [1, 2]
    return {"pass_bins": pass_bins, "all_bins": all_bins}

@router.get("/lot/{lot_id}/wafer_bin_map")
def get_wafer_bin_map(
    lot_id: int,
    data_range: str = Query("final"),
    sites: str = Query("all"),
    db: Session = Depends(get_db)
):
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot or not lot.parquet_path:
        raise HTTPException(status_code=404, detail="数据不存在")

    import pandas as pd
    df = pd.read_parquet(lot.parquet_path)

    if 'X_COORD' not in df.columns or 'Y_COORD' not in df.columns:
        return {"data": [], "has_map": False}

    df = df.dropna(subset=['X_COORD', 'Y_COORD', 'SOFT_BIN'])

    # Site过滤
    if sites != 'all':
        site_list = [int(s) for s in sites.split(',')]
        df = df[df['SITE_NUM'].isin(site_list)]

    # 找复测坐标
    df['key'] = df['X_COORD'].astype(int).astype(str) + ',' + df['Y_COORD'].astype(int).astype(str)
    counts = df['key'].value_counts()
    retest_keys = set(counts[counts > 1].index)

    # 按data_range去重
    if data_range == 'final':
        df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')
    elif data_range == 'original':
        df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='first')

    # 构造结果
    df['is_retest'] = df['key'].isin(retest_keys)
    
    result = []
    # 转换为 dict 列表，比 iterrows 快得多
    temp_df = df[['X_COORD', 'Y_COORD', 'SOFT_BIN', 'is_retest']].copy()
    temp_df.columns = ['x', 'y', 'bin', 'retest']
    temp_df['x'] = temp_df['x'].astype(int)
    temp_df['y'] = temp_df['y'].astype(int)
    temp_df['bin'] = temp_df['bin'].astype(int)
    
    result = temp_df.to_dict('records')

    return {"data": result, "has_map": True}


@router.get("/lot/{lot_id}/bin_summary")
def get_bin_summary(
    lot_id: int,
    data_range: str = Query("final"),
    sites: str = Query("all"),
    db: Session = Depends(get_db),
):
    """获取Bin汇总数据"""
    query = db.query(BinSummary).filter(
        and_(
            BinSummary.lot_id == lot_id,
            BinSummary.site == 0,
            BinSummary.data_range == data_range
        )
    ).order_by(BinSummary.count.desc())

    bins_all = query.all()

    # 获取所有site列表
    all_sites_query = db.query(BinSummary.site).filter(
        and_(
            BinSummary.lot_id == lot_id,
            BinSummary.site > 0,
            BinSummary.data_range == data_range
        )
    ).distinct().all()
    all_site_list = sorted([s[0] for s in all_sites_query])

    # 按sites参数过滤
    if sites != 'all':
        site_filter = [int(s) for s in sites.split(',')]
    else:
        site_filter = all_site_list

    result = []
    for b in bins_all:
        row = {
            "bin_number": b.bin_number,
            "bin_name": b.bin_name,
            "all_site_count": b.count,
            "all_site_pct": b.percentage,
            "comment": b.comment,
            "sites": {}
        }
        for site in site_filter:
            site_bin = db.query(BinSummary).filter(
                and_(
                    BinSummary.lot_id == lot_id,
                    BinSummary.bin_number == b.bin_number,
                    BinSummary.site == site,
                    BinSummary.data_range == data_range
                )
            ).first()
            if site_bin:
                row["sites"][f"site{site}"] = {
                    "count": site_bin.count,
                    "pct": site_bin.percentage
                }
        result.append(row)

    return {"bins": result, "sites": site_filter, "all_sites": all_site_list}

class BinCommentUpdate(BaseModel):
    bin_number: int
    comment: str

@router.post("/lot/{lot_id}/bin_comment")
def update_bin_comment(
    lot_id: int,
    data: BinCommentUpdate,
    db: Session = Depends(get_db),
):
    """更新Bin的备注信息"""
    bins = db.query(BinSummary).filter(
        and_(
            BinSummary.lot_id == lot_id,
            BinSummary.bin_number == data.bin_number
        )
    ).all()
    
    for b in bins:
        b.comment = data.comment
    db.commit()
    return {"status": "success"}

@router.get("/lot/{lot_id}/retest_analysis")
def get_retest_analysis(
    lot_id: int,
    sites: str = Query("all"),
    db: Session = Depends(get_db),
):
    """复测分析：Bin转移情况"""
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot or not lot.parquet_path:
        raise HTTPException(status_code=404, detail="数据不存在")

    import pandas as pd
    df = pd.read_parquet(lot.parquet_path)

    if 'X_COORD' not in df.columns or 'Y_COORD' not in df.columns:
        return {"has_retest": False, "details": [], "summary": []}

    df = df.dropna(subset=['X_COORD', 'Y_COORD', 'SOFT_BIN'])

    # Site过滤
    if sites != 'all':
        site_list = [int(s) for s in sites.split(',')]
        df = df[df['SITE_NUM'].isin(site_list)]

    # 找复测坐标（出现超过一次）
    coord_groups = df.groupby(['X_COORD', 'Y_COORD'])
    retest_details = []

    for (x, y), group in coord_groups:
        if len(group) < 2:
            continue
        first = group.iloc[0]
        last = group.iloc[-1]

        first_bin = int(first['SOFT_BIN'])
        last_bin = int(last['SOFT_BIN'])
        first_site = int(first['SITE_NUM'])
        last_site = int(last['SITE_NUM'])

        # 获取bin名称
        bin_defs: dict = {}
        if hasattr(lot, '_bin_defs'):
            bin_defs = lot._bin_defs

        retest_details.append({
            "x": int(x),
            "y": int(y),
            "first_site": first_site,
            "first_bin": first_bin,
            "last_site": last_site,
            "last_bin": last_bin,
            "site_changed": first_site != last_site,
            "retest_count": len(group) - 1,
        })

    if not retest_details:
        return {"has_retest": False, "details": [], "summary": [], "totals": {}}

    # 获取pass bins
    bin_defs_data = db.query(BinSummary).filter(
        and_(BinSummary.lot_id == lot_id, BinSummary.site == 0,
             BinSummary.data_range == 'final')
    ).all()

    # 用数量最多的bin判断pass（临时逻辑，后续可从bin定义读）
    pass_bins_query = db.query(BinSummary).filter(
        and_(BinSummary.lot_id == lot_id, BinSummary.site == 0,
             BinSummary.data_range == 'final')
    ).all()

    from app.api.routes.analysis import _get_pass_bins
    pass_bins = _get_pass_bins(lot_id, db)

    def get_direction(fb, lb):
        fb_pass = fb in pass_bins
        lb_pass = lb in pass_bins
        if fb_pass and lb_pass:
            return "pass_pass"
        elif not fb_pass and lb_pass:
            return "fail_pass"
        elif fb_pass and not lb_pass:
            return "pass_fail"
        else:
            return "fail_fail"

    # 转移汇总：按 first_bin → last_bin 分组统计
    from collections import defaultdict
    transfer_counts = defaultdict(int)
    for d in retest_details:
        key = (d['first_bin'], d['last_bin'])
        transfer_counts[key] += 1

    summary = []
    for (fb, lb), cnt in sorted(transfer_counts.items(), key=lambda x: (-x[1], x[0][0])):
        summary.append({
            "from_bin": fb,
            "to_bin": lb,
            "count": cnt,
            "direction": get_direction(fb, lb),
            "no_change": fb == lb,
        })

    # 总计统计
    directions = [get_direction(d['first_bin'], d['last_bin']) for d in retest_details]
    totals = {
        "total_retest_dies": len(retest_details),
        "fail_to_pass": directions.count("fail_pass"),
        "pass_to_fail": directions.count("pass_fail"),
        "fail_to_fail": directions.count("fail_fail"),
        "pass_to_pass": directions.count("pass_pass"),
    }

    return {
        "has_retest": True,
        "details": retest_details[:500],  # 最多返回500条明细
        "summary": summary,
        "totals": totals,
    }


def _get_pass_bins(lot_id: int, db) -> list:
    """从bin_summary推断pass bins"""
    from app.models.bin_summary import BinSummary
    from sqlalchemy import and_
    bins = db.query(BinSummary).filter(
        and_(BinSummary.lot_id == lot_id,
             BinSummary.site == 0,
             BinSummary.data_range == 'final')
    ).order_by(BinSummary.count.desc()).all()
    if not bins:
        return [1, 2]
    # 数量最多的bin通常是pass bin，取占比超过50%的
    total = sum(b.count for b in bins)
    pass_bins = [b.bin_number for b in bins if b.count / total > 0.3]
    return pass_bins if pass_bins else [bins[0].bin_number]


@router.get("/lot/{lot_id}/param_data")
def get_param_data(
    lot_id: int,
    param_name: str = Query(...),
    filter_type: str = Query("all"),
    sigma: float = Query(3.0),
    sites: str = Query("all"),
    data_range: str = Query("final"),
    custom_min: Optional[float] = Query(None),
    custom_max: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    """
    获取单个参数的原始数据（用于直方图/Scatter/WaferMap）
    filter_type: all / robust / filter_by_limit / filter_by_sigma / custom
    sites: all 或 逗号分隔的site编号 如 "1,2"
    data_range: final / original / all
    """
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot or not lot.parquet_path:
        raise HTTPException(status_code=404, detail="数据文件不存在")

    # 读取Parquet
    try:
        df = pd.read_parquet(lot.parquet_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取数据失败: {e}")

    if param_name not in df.columns:
        raise HTTPException(status_code=404, detail=f"参数 {param_name} 不存在")

    # 坐标去重
    if 'X_COORD' in df.columns and 'Y_COORD' in df.columns:
        if data_range == 'final':
            df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')
        elif data_range == 'original':
            df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='first')

    # Site筛选
    if sites != 'all':
        site_list = [int(s) for s in sites.split(',')]
        df = df[df['SITE_NUM'].isin(site_list)]

    # 获取参数的limit
    item = db.query(TestItem).filter(
        and_(
            TestItem.lot_id == lot_id,
            TestItem.item_name == param_name,
            TestItem.site == 0
        )
    ).first()
    ll = item.lower_limit if item else None
    ul = item.upper_limit if item else None
    unit = item.unit if item else ''

    # 应用Filter
    from app.services.stats import apply_filter, calc_param_stats

    result_data = []

    # ── 先计算 All Sites (site=0) ─────────────────────────
    all_values = df[param_name].dropna().values.astype(float)
    filtered_all = apply_filter(all_values, filter_type, ll, ul, sigma, custom_min, custom_max)
    all_stats = calc_param_stats(filtered_all, ll, ul, len(filtered_all))

    # 用 All Sites 过滤后数据计算全局统一 bin edges
    # 所有 Site 的直方图共用这套 edges，确保 X 轴对齐
    NUM_BINS = 50
    exceeds_limit = False   # 数据是否超限
    ll_bin_index = None     # LL 在第几个 bin 边界
    ul_bin_index = None     # UL 在第几个 bin 边界

    if len(filtered_all) > 1:
        global_min = float(np.min(filtered_all))
        global_max = float(np.max(filtered_all))

        if global_min == global_max:
            center = global_min
            half = abs(center) * 0.5 if center != 0 else 0.5
            global_min = center - half
            global_max = center + half
            _, global_edges = np.histogram(filtered_all, bins=NUM_BINS,
                                           range=(global_min, global_max))
        elif ll is not None and ul is not None and ll != ul and (global_min < ll or global_max > ul):
            # ── 数据超限：非均匀分bin ──
            # LL放在20%位置(bin #10), UL放在80%位置(bin #40)
            # 10 bins: [left_bound, LL]
            # 30 bins: [LL, UL]
            # 10 bins: [UL, right_bound]
            exceeds_limit = True
            n_below = 10
            n_mid = 30
            n_above = 10
            ll_bin_index = n_below       # LL 在 edge[10]
            ul_bin_index = n_below + n_mid  # UL 在 edge[40]

            # 左边界：取 min(数据最小值, LL)，加少量margin
            left_bound = min(global_min, ll)
            left_margin = (ul - ll) * 0.03
            left_bound = left_bound - left_margin

            # 右边界：取 max(数据最大值, UL)，加少量margin
            right_bound = max(global_max, ul)
            right_margin = (ul - ll) * 0.03
            right_bound = right_bound + right_margin

            edges_below = np.linspace(left_bound, ll, n_below + 1)
            edges_mid = np.linspace(ll, ul, n_mid + 1)
            edges_above = np.linspace(ul, right_bound, n_above + 1)

            # 合并，去掉重复的边界点
            global_edges = np.concatenate([edges_below, edges_mid[1:], edges_above[1:]])
        else:
            # 数据在限内或无双边Limit：均匀分bin
            _, global_edges = np.histogram(filtered_all, bins=NUM_BINS,
                                           range=(global_min, global_max))
    else:
        global_edges = np.linspace(0, 1, NUM_BINS + 1)

    NUM_BINS = len(global_edges) - 1  # 实际 bin 数量（非均匀时仍为50）
    global_edges_list = [round(float(e), 6) for e in global_edges.tolist()]

    result_data.append({
        "site": 0,
        "histogram": {"counts": [], "edges": global_edges_list},
        "scatter": [],
        "wafer_map": [],
        "stats": all_stats,
    })

    # ── 再按 Site 分组 ────────────────────────────────────
    site_groups = df.groupby('SITE_NUM')

    for site_num, site_df in site_groups:
        values = site_df[param_name].dropna().values.astype(float)
        filtered = apply_filter(values, filter_type, ll, ul, sigma, custom_min, custom_max)

        # Scatter数据：测试序号+值
        scatter = []
        for idx, row in site_df.iterrows():
            val = row[param_name]
            if pd.notna(val):
                scatter.append({
                    "idx": int(idx),
                    "val": float(val)
                })

        # WaferMap数据
        wafer_map = []
        if 'X_COORD' in site_df.columns:
            for _, row in site_df.iterrows():
                if pd.notna(row[param_name]) and pd.notna(row.get('X_COORD')) and pd.notna(row.get('Y_COORD')):
                    wafer_map.append({
                        "x": int(row['X_COORD']),
                        "y": int(row['Y_COORD']),
                        "val": float(row[param_name])
                    })

        # 直方图：使用全局 edges 分箱
        if len(filtered) > 0:
            hist, _ = np.histogram(filtered, bins=global_edges)
            histogram = {
                "counts": hist.tolist(),
                "edges": global_edges_list,
            }
        else:
            histogram = {"counts": [0] * NUM_BINS, "edges": global_edges_list}

        stats = calc_param_stats(filtered, ll, ul, len(filtered))

        result_data.append({
            "site": int(site_num),
            "histogram": histogram,
            "scatter": scatter,
            "wafer_map": wafer_map,
            "stats": stats,
        })

    return {
        "param_name": param_name,
        "unit": unit,
        "lower_limit": ll,
        "upper_limit": ul,
        "filter_type": filter_type,
        "data_range": data_range,
        "global_edges": global_edges_list,
        "exceeds_limit": exceeds_limit,
        "ll_bin_index": ll_bin_index,
        "ul_bin_index": ul_bin_index,
        "sites": result_data,
    }


# ── 多LOT分析 API ─────────────────────────────────────────

@router.get("/multi/items")
def get_multi_lot_items(
    lot_ids: str = Query(..., description="逗号分隔的lot id，如 1,2,3"),
    db: Session = Depends(get_db),
):
    """
    多LOT参数汇总表：返回每个LOT的 site=0 参数统计
    响应结构:
    {
      lots: [{id, filename, lot_id}],
      params: [{item_number, item_name, unit, lower_limit, upper_limit,
                lots: {lot_id: {mean,stdev,min_val,max_val,cpk,yield_rate,fail_count}}}]
    }
    """
    ids = [int(x) for x in lot_ids.split(",") if x.strip()]
    lots = db.query(Lot).filter(Lot.id.in_(ids)).all()
    lot_map = {l.id: l for l in lots}
    # 保持用户传入顺序
    ordered_lots = [lot_map[i] for i in ids if i in lot_map]

    # 以第一个LOT的参数顺序为基准
    if not ordered_lots:
        raise HTTPException(status_code=404, detail="LOT不存在")

    ref_items = db.query(TestItem).filter(
        TestItem.lot_id == ordered_lots[0].id,
        TestItem.site == 0
    ).order_by(TestItem.item_number).all()

    params = []
    for ref in ref_items:
        row = {
            "item_number": ref.item_number,
            "item_name": ref.item_name,
            "unit": ref.unit,
            "lower_limit": ref.lower_limit,
            "upper_limit": ref.upper_limit,
            "lots": {}
        }
        for lot in ordered_lots:
            item = db.query(TestItem).filter(
                TestItem.lot_id == lot.id,
                TestItem.item_name == ref.item_name,
                TestItem.site == 0
            ).first()
            if item:
                row["lots"][str(lot.id)] = {
                    "mean": item.mean,
                    "stdev": item.stdev,
                    "min_val": item.min_val,
                    "max_val": item.max_val,
                    "cpk": item.cpk,
                    "yield_rate": item.yield_rate,
                    "fail_count": item.fail_count,
                    "exec_qty": item.exec_qty,
                }
        params.append(row)

    return {
        "lots": [{"id": l.id, "filename": l.filename, "lot_id": l.lot_id} for l in ordered_lots],
        "params": params,
    }


@router.get("/multi/param_hist")
def get_multi_lot_param_hist(
    lot_ids: str = Query(...),
    param_name: str = Query(...),
    filter_type: str = Query("all"),
    sigma: float = Query(3.0),
    data_range: str = Query("final"),
    custom_min: Optional[float] = Query(None),
    custom_max: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    """
    多LOT单参数直方图数据，各LOT共用同一套 global_edges
    """
    from app.services.stats import apply_filter, calc_param_stats

    ids = [int(x) for x in lot_ids.split(",") if x.strip()]
    lots = db.query(Lot).filter(Lot.id.in_(ids)).all()
    lot_map = {l.id: l for l in lots}
    ordered_lots = [lot_map[i] for i in ids if i in lot_map]

    # 获取 limit/unit（从第一个LOT）
    ref_item = db.query(TestItem).filter(
        TestItem.lot_id == ordered_lots[0].id,
        TestItem.item_name == param_name,
        TestItem.site == 0
    ).first()
    ll = ref_item.lower_limit if ref_item else None
    ul = ref_item.upper_limit if ref_item else None
    unit = ref_item.unit if ref_item else ""

    # 先收集所有LOT的全部数据，计算全局 edges
    all_values_combined = []
    lot_values: dict = {}
    for lot in ordered_lots:
        if not lot.parquet_path or not os.path.exists(lot.parquet_path):
            lot_values[lot.id] = np.array([])
            continue
        df = pd.read_parquet(lot.parquet_path)
        if param_name not in df.columns:
            lot_values[lot.id] = np.array([])
            continue
        if 'X_COORD' in df.columns and 'Y_COORD' in df.columns:
            if data_range == 'final':
                df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')
            elif data_range == 'original':
                df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='first')
        vals = df[param_name].dropna().values.astype(float)
        filtered = apply_filter(vals, filter_type, ll, ul, sigma, custom_min, custom_max)
        lot_values[lot.id] = filtered
        all_values_combined.extend(filtered.tolist())

    all_arr = np.array(all_values_combined)
    NUM_BINS = 50
    if len(all_arr) > 1:
        gmin, gmax = float(np.min(all_arr)), float(np.max(all_arr))
        if gmin == gmax:
            center = gmin
            half = abs(center) * 0.5 if center != 0 else 0.5
            gmin = center - half; gmax = center + half
        _, global_edges = np.histogram(all_arr, bins=NUM_BINS, range=(gmin, gmax))
    else:
        global_edges = np.linspace(0, 1, NUM_BINS + 1)
    global_edges_list = [round(float(e), 6) for e in global_edges.tolist()]

    result = []
    for lot in ordered_lots:
        vals = lot_values.get(lot.id, np.array([]))
        if len(vals) > 0:
            counts, _ = np.histogram(vals, bins=global_edges)
            counts_list = counts.tolist()
        else:
            counts_list = [0] * NUM_BINS
        stats = calc_param_stats(vals, ll, ul, len(vals)) if len(vals) > 0 else {}
        result.append({
            "lot_id": lot.id,
            "filename": lot.filename,
            "counts": counts_list,
            "stats": stats,
        })

    return {
        "param_name": param_name,
        "unit": unit,
        "lower_limit": ll,
        "upper_limit": ul,
        "global_edges": global_edges_list,
        "lots": result,
    }


@router.get("/multi/bin_summary")
def get_multi_lot_bin_summary(
    lot_ids: str = Query(...),
    data_range: str = Query("final"),
    db: Session = Depends(get_db),
):
    """
    多LOT Bin汇总：行=Bin，列=各LOT
    """
    ids = [int(x) for x in lot_ids.split(",") if x.strip()]
    lots = db.query(Lot).filter(Lot.id.in_(ids)).all()
    lot_map = {l.id: l for l in lots}
    ordered_lots = [lot_map[i] for i in ids if i in lot_map]

    # 收集所有 bin_number
    all_bin_numbers = set()
    lot_bin_data: dict = {}
    for lot in ordered_lots:
        bins = db.query(BinSummary).filter(
            BinSummary.lot_id == lot.id,
            BinSummary.site == 0,
            BinSummary.data_range == data_range
        ).all()
        lot_bin_data[lot.id] = {b.bin_number: b for b in bins}
        all_bin_numbers.update(b.bin_number for b in bins)

    sorted_bins = sorted(all_bin_numbers)

    # 获取 bin_name（从任意一个LOT）
    bin_names: dict = {}
    for lot in ordered_lots:
        for bn, b in lot_bin_data[lot.id].items():
            if bn not in bin_names:
                bin_names[bn] = b.bin_name

    rows = []
    for bn in sorted_bins:
        row = {
            "bin_number": bn,
            "bin_name": bin_names.get(bn, f"Bin{bn}"),
            "lots": {}
        }
        for lot in ordered_lots:
            b = lot_bin_data[lot.id].get(bn)
            row["lots"][str(lot.id)] = {
                "count": b.count if b else 0,
                "pct": b.percentage if b else 0.0,
            }
        rows.append(row)

    return {
        "lots": [{"id": l.id, "filename": l.filename, "lot_id": l.lot_id} for l in ordered_lots],
        "bins": rows,
    }


@router.get("/multi/wafer_bin_maps")
def get_multi_lot_wafer_bin_maps(
    lot_ids: str = Query(...),
    data_range: str = Query("final"),
    db: Session = Depends(get_db),
):
    """
    多LOT Wafer Bin Map，每个LOT返回独立的 map 数据
    """
    ids = [int(x) for x in lot_ids.split(",") if x.strip()]
    lots = db.query(Lot).filter(Lot.id.in_(ids)).all()
    lot_map = {l.id: l for l in lots}
    ordered_lots = [lot_map[i] for i in ids if i in lot_map]

    result = []
    for lot in ordered_lots:
        if not lot.parquet_path or not os.path.exists(lot.parquet_path):
            result.append({"lot_id": lot.id, "filename": lot.filename, "has_map": False, "data": []})
            continue
        df = pd.read_parquet(lot.parquet_path)
        if 'X_COORD' not in df.columns or 'Y_COORD' not in df.columns:
            result.append({"lot_id": lot.id, "filename": lot.filename, "has_map": False, "data": []})
            continue
        df = df.dropna(subset=['X_COORD', 'Y_COORD', 'SOFT_BIN'])
        if data_range == 'final':
            df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')
        elif data_range == 'original':
            df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='first')
        tmp = df[['X_COORD', 'Y_COORD', 'SOFT_BIN']].copy()
        tmp.columns = ['x', 'y', 'bin']
        tmp['x'] = tmp['x'].astype(int)
        tmp['y'] = tmp['y'].astype(int)
        tmp['bin'] = tmp['bin'].astype(int)
        result.append({
            "lot_id": lot.id,
            "filename": lot.filename,
            "lot_id_str": lot.lot_id,
            "has_map": True,
            "data": tmp.to_dict('records'),
        })

    return {"maps": result}