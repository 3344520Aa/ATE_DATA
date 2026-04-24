import os
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List
from fastapi.responses import StreamingResponse
import io
from pydantic import BaseModel
import pandas as pd
import numpy as np
from app.core.database import get_db
from app.models.test_item import TestItem
from app.models.bin_summary import BinSummary
from app.models.lot import Lot
# 延后导入，防止环境缺少依赖导致后端无法启动

router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.get("/lot/{lot_id}/items_summary")
def get_test_items_summary(
    lot_id: int,
    filter_type: str = Query("all"),
    sigma: float = Query(3.0),
    data_range: str = Query("final"),
    db: Session = Depends(get_db),
):
    """根据过滤器计算所有参数的统计数据"""
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot or not lot.parquet_path:
        raise HTTPException(status_code=404, detail="数据不存在")

    df = pd.read_parquet(lot.parquet_path)
    
    # 坐标去重
    if 'X_COORD' in df.columns and 'Y_COORD' in df.columns:
        if data_range == 'final':
            df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')
        elif data_range == 'original':
            df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='first')

    # 获取所有参数名和Limit (从 site=0 的 TestItem 记录中读取)
    items = db.query(TestItem).filter(
        and_(TestItem.lot_id == lot_id, TestItem.site == 0)
    ).order_by(TestItem.item_number).all()

    from app.services.stats import apply_filter, calc_param_stats

    result = []
    for item in items:
        if item.item_name not in df.columns:
            continue
            
        values = df[item.item_name].values.astype(float)
        exec_qty = int(df[item.item_name].notna().sum())
        
        # 应用过滤
        filtered_values = apply_filter(values, filter_type, item.lower_limit, item.upper_limit, sigma)
        
        # 计算统计
        stats = calc_param_stats(filtered_values, item.lower_limit, item.upper_limit, exec_qty)
        
        result.append({
            "id": item.id,
            "item_number": item.item_number,
            "item_name": item.item_name,
            "unit": item.unit,
            "lower_limit": item.lower_limit,
            "upper_limit": item.upper_limit,
            **stats
        })

    return result

@router.get("/lot/{lot_id}/export_items")
def export_test_items(
    lot_id: int,
    filter_type: str = Query("all"),
    sigma: float = Query(3.0),
    data_range: str = Query("final"),
    chars_row: int = Query(3),
    selected_items: str = Query(""),
    db: Session = Depends(get_db),
):
    """导出完整Excel报告：Sheet1汇总+统计，Sheet2直方图，Sheet3 Bin汇总+Map"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import xlsxwriter
    except ImportError:
        raise HTTPException(status_code=500, detail="服务器缺少必要依赖 (matplotlib, xlsxwriter)，请联系管理员安装")

    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="LOT不存在")

    # 1. 获取数据
    lot_info = get_lot_info(lot_id, db)
    items_summary = get_test_items_summary(lot_id, filter_type, sigma, data_range, db)
    
    if selected_items:
        try:
            sel_nums = [int(x.strip()) for x in selected_items.split(',') if x.strip()]
            if sel_nums:
                items_summary = [it for it in items_summary if it['item_number'] in sel_nums]
        except ValueError:
            pass

    bin_data = get_bin_summary(lot_id, data_range, "all", db)
    map_result = get_wafer_bin_map(lot_id, data_range, "all", db)

    # 预读数据，避免循环内重复读取 Parquet
    df_all = pd.read_parquet(lot.parquet_path)
    if 'X_COORD' in df_all.columns and 'Y_COORD' in df_all.columns:
        if data_range == 'final':
            df_all = df_all.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')
        elif data_range == 'original':
            df_all = df_all.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='first')

    output = io.BytesIO()
    # 使用 xlsxwriter 引擎以支持图片插入
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # ─── Sheet 1: Stats & Info ───
        stats_sheet = workbook.add_worksheet('Stats')
        info_labels = {
            "filename": "名称", "program": "程序", "test_machine": "测试机",
            "station_count": "工位数", "die_count": "测试数量",
            "yield_rate": "良率", "data_type": "测试阶段", "test_date": "测试日期"
        }
        row = 0
        for key, label in info_labels.items():
            val = lot_info.get(key)
            if key == 'yield_rate' and val is not None:
                val = f"{val*100:.2f}%"
            elif key == 'test_date' and val:
                try:
                    from datetime import datetime
                    if isinstance(val, str):
                        val = datetime.fromisoformat(val).strftime('%Y-%m-%d %H:%M:%S')
                except: pass
            stats_sheet.write(row, 0, label)
            stats_sheet.write(row, 1, str(val))
            row += 1
        
        row += 1 # 空一行
        df_stats = pd.DataFrame(items_summary)
        if not df_stats.empty:
            column_mapping = {
                'item_number': '#', 'item_name': 'TestItem', 'lower_limit': 'L.Limit',
                'upper_limit': 'U.Limit', 'unit': 'Units', 'min_val': 'Min',
                'max_val': 'Max', 'exec_qty': 'Exec Qty', 'fail_count': 'Failures',
                'fail_rate': 'Fail Rate', 'yield_rate': 'Yield', 'mean': 'Mean',
                'stdev': 'Stdev', 'cpu': 'CPU', 'cpl': 'CPL', 'cpk': 'CPK'
            }
            existing_cols = [c for c in column_mapping.keys() if c in df_stats.columns]
            df_stats = df_stats[existing_cols].rename(columns=column_mapping)
            # 格式化百分比
            if 'Fail Rate' in df_stats.columns:
                df_stats['Fail Rate'] = df_stats['Fail Rate'].apply(lambda x: f"{x*100:.3f}%" if pd.notna(x) else "0%")
            if 'Yield' in df_stats.columns:
                df_stats['Yield'] = df_stats['Yield'].apply(lambda x: f"{x*100:.2f}%" if pd.notna(x) else "-")
            
            df_stats.to_excel(writer, sheet_name='Stats', startrow=row, index=False)

        # ─── Sheet 2: Histograms ───
        hist_sheet = workbook.add_worksheet('Histograms')
        hist_sheet.set_column(0, 50, 10) # 设置默认列宽
        
        from app.services.stats import apply_filter, calc_param_stats, calc_hist_edges, calc_hist_x_range
        
        # 复用 figure 以提升速度
        fig, ax = plt.subplots(figsize=(6, 4)) # (6, 4) 表示宽 6 英寸，高 4 英寸
        SITE_COLORS = ['#ff6b6b', '#4dabf7', '#69db7c', '#ffd43b', '#e599f7', '#74c0fc', '#a9e34b', '#ffa94d']
        
        for i, item in enumerate(items_summary):
            p_name = item['item_name']
            p_num = item['item_number']
            
            if p_name not in df_all.columns: continue
            
            # 获取 limit 和原始数据
            ll, ul = item.get('lower_limit'), item.get('upper_limit')
            unit = item.get('unit') or ''
            
            vals = df_all[p_name].dropna().values.astype(float)
            if len(vals) == 0: continue
            
            filtered_all = apply_filter(vals, filter_type, ll, ul, sigma)
            if len(filtered_all) == 0: continue
            
            # 计算全局 Edges 和判断是否超限模式
            edges, exceeds_limit, ll_bin_idx, ul_bin_idx = calc_hist_edges(filtered_all, ll, ul)
            
            # 获取各 Site 数据
            sites_data = []
            if 'SITE_NUM' in df_all.columns:
                site_groups = df_all.dropna(subset=[p_name]).groupby('SITE_NUM')
                for site_num, site_df in site_groups:
                    if site_num == 0: continue
                    site_vals = site_df[p_name].values.astype(float)
                    site_filtered = apply_filter(site_vals, filter_type, ll, ul, sigma)
                    if len(site_filtered) > 0:
                        counts, _ = np.histogram(site_filtered, bins=edges)
                        sites_data.append({'site': int(site_num), 'counts': counts})
            
            if not sites_data:
                counts, _ = np.histogram(filtered_all, bins=edges)
                sites_data.append({'site': 0, 'counts': counts})

            ax.clear()
            ax.set_axisbelow(True)
            ax.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)
            
            # 计算 Site 0 统计用于标题
            s0_stats = calc_param_stats(filtered_all, ll, ul, len(filtered_all))
            
            data_min, data_max = float(np.min(filtered_all)), float(np.max(filtered_all))
            edges_min, edges_max = float(edges[0]), float(edges[-1])
            x_range_info = calc_hist_x_range(data_min, data_max, ll, ul, edges_min, edges_max)
            x_min, x_max = x_range_info['x_min'], x_range_info['x_max']
            
            if exceeds_limit:
                x_pos = np.arange(len(edges) - 1)
                for idx, s in enumerate(sites_data):
                    color = SITE_COLORS[idx % len(SITE_COLORS)]
                    ax.bar(x_pos, s['counts'], width=0.9, alpha=0.7, color=color, label=f"Site{s['site']}", zorder=3)
                
                if ll_bin_idx is not None:
                    ax.axvline(ll_bin_idx, color='red', linestyle='--', linewidth=1.5, zorder=4)
                    ax.text(ll_bin_idx, ax.get_ylim()[1]*0.5, f'LL:{ll}', color='red', fontsize=7, ha='left', va='center', rotation=90)
                if ul_bin_idx is not None:
                    ax.axvline(ul_bin_idx, color='red', linestyle='--', linewidth=1.5, zorder=4)
                    ax.text(ul_bin_idx, ax.get_ylim()[1]*0.5, f'UL:{ul}', color='red', fontsize=7, ha='right', va='center', rotation=90)
                
                # 选取 11 个 tick
                tick_indices = np.linspace(0, len(edges)-2, 11).astype(int)
                ax.set_xticks(tick_indices)
                ax.set_xticklabels([f"{edges[t]:.3f}" for t in tick_indices], rotation=30)
            else:
                bin_centers = (edges[:-1] + edges[1:]) / 2
                bin_w = edges[1] - edges[0] if len(edges) > 1 else 1
                for idx, s in enumerate(sites_data):
                    color = SITE_COLORS[idx % len(SITE_COLORS)]
                    ax.bar(bin_centers, s['counts'], width=bin_w * 0.8, alpha=0.7, color=color, label=f"Site{s['site']}", zorder=3)
                
                ax.set_xlim(x_min, x_max)
                if ll is not None:
                    ax.axvline(ll, color='red', linestyle='--', linewidth=1.5, zorder=4)
                    ax.text(ll, ax.get_ylim()[1]*0.5, f'LL:{ll}', color='red', fontsize=7, ha='left', va='center', rotation=90)
                if ul is not None:
                    ax.axvline(ul, color='red', linestyle='--', linewidth=1.5, zorder=4)
                    ax.text(ul, ax.get_ylim()[1]*0.5, f'UL:{ul}', color='red', fontsize=7, ha='right', va='center', rotation=90)
                
                ax.set_xticks(x_range_info['ticks'])
                ax.xaxis.set_major_formatter(plt.FormatStrFormatter('%.3f'))
                ax.tick_params(axis='x', rotation=30)
            
            # Sigma 线
            if filter_type == 'filter_by_sigma':
                sigma_val = float(sigma) if sigma else 3.0
                sigma_l, sigma_u = s0_stats['mean'] - sigma_val * s0_stats['stdev'], s0_stats['mean'] + sigma_val * s0_stats['stdev']
                if exceeds_limit:
                    def find_bin(val):
                        for b_i in range(len(edges)-1):
                            if edges[b_i] <= val <= edges[b_i+1]: return b_i
                        return 0 if val < edges[0] else len(edges)-2
                    ax.axvline(find_bin(sigma_l), color='#00c853', linestyle='--', linewidth=1, zorder=4)
                    ax.axvline(find_bin(sigma_u), color='#00c853', linestyle='--', linewidth=1, zorder=4)
                else:
                    ax.axvline(sigma_l, color='#00c853', linestyle='--', linewidth=1, zorder=4)
                    ax.axvline(sigma_u, color='#00c853', linestyle='--', linewidth=1, zorder=4)
            
            title_stats = (
                f"Min={s0_stats['min_val']:.4f} Max={s0_stats['max_val']:.4f} "
                f"Mean={s0_stats['mean']:.4f} Stdev={s0_stats['stdev']:.4f} CPK={s0_stats['cpk'] if s0_stats['cpk'] is not None else 0:.4f}"
            )
            ax.set_title(f"{p_num}.{p_name}\n{title_stats}", fontsize=8)
            ax.set_ylabel("Parts", fontsize=8)
            ax.set_xlabel(unit, fontsize=8)
            ax.tick_params(labelsize=7)
            
            # 添加图例在下方
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.22), ncol=4, fontsize=7, frameon=False)
            
            fig.tight_layout()
            img_data = io.BytesIO()
            plt.savefig(img_data, format='png', dpi=100)
            img_data.seek(0)
            
            # 计算位置 (600x400 图片对应约 9.4列宽, 20行高。设间距为 10列 和 20行 使其紧凑挨在一起)
            r_idx = (i // chars_row) * 18
            c_idx = (i % chars_row) * 7
            hist_sheet.insert_image(r_idx, c_idx, 
            f'h_{i}.png', {
                'image_data': img_data,
                'x_scale': 0.9,
                'y_scale': 0.9
            })
        plt.close(fig) # 循环结束后关闭

        # ─── Sheet 3: Bin Info & Map ───
        bin_sheet = workbook.add_worksheet('BinInfo')
        # 表头
        for r, (key, label) in enumerate(info_labels.items()):
            val = lot_info.get(key)
            if key == 'yield_rate' and val is not None:
                val = f"{val*100:.2f}%"
            bin_sheet.write(r, 0, label)
            bin_sheet.write(r, 1, str(val))
        
        # Bin 表格
        row = len(info_labels) + 1
        sites = bin_data['sites']
        headers = ['Bin', 'Name', 'Total Count', 'Total %'] + [f'Site{s}' for s in sites]
        for c, h in enumerate(headers):
            bin_sheet.write(row, c, h)
        
        row += 1
        for b in bin_data['bins']:
            bin_sheet.write(row, 0, b['bin_number'])
            bin_sheet.write(row, 1, b['bin_name'])
            bin_sheet.write(row, 2, b['all_site_count'])
            bin_sheet.write(row, 3, f"{b['all_site_pct']:.2f}%")
            for i, s in enumerate(sites):
                cnt = b['sites'].get(f'site{s}', {}).get('count', 0)
                bin_sheet.write(row, 4 + i, cnt)
            row += 1
        
        # Wafer Map
        row += 2
        if map_result['has_map'] and map_result['data']:
            df_map = pd.DataFrame(map_result['data'])
            fig, ax = plt.subplots(figsize=(6, 5))
            scatter = ax.scatter(df_map['x'], df_map['y'], c=df_map['bin'], cmap='prism', s=15, marker='s')
            ax.set_aspect('equal')
            ax.invert_yaxis()
            ax.set_title('Wafer Bin Map', fontsize=12)
            plt.colorbar(scatter, ax=ax, label='Bin Number')
            
            img_data = io.BytesIO()
            plt.savefig(img_data, format='png', dpi=90, bbox_inches='tight')
            plt.close(fig)
            img_data.seek(0)
            bin_sheet.insert_image(row, 0, 'wafer_map.png', {'image_data': img_data})

    output.seek(0)
    filename = f"LOT_{lot_id}_FullReport_{filter_type}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


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
    temp_df = df[['X_COORD', 'Y_COORD', 'SOFT_BIN', 'SITE_NUM', 'is_retest']].copy()
    temp_df.columns = ['x', 'y', 'bin', 'site', 'retest']
    temp_df['x'] = temp_df['x'].round().astype(int)
    temp_df['y'] = temp_df['y'].round().astype(int)
    temp_df['bin'] = temp_df['bin'].astype(int)
    temp_df['site'] = temp_df['site'].astype(int)
    
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
    from app.services.stats import calc_hist_edges
    global_edges, exceeds_limit, ll_bin_index, ul_bin_index = calc_hist_edges(filtered_all, ll, ul)

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