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
from fastapi import BackgroundTasks
import uuid
import time
# 延后导入，防止环境缺少依赖导致后端无法启动

router = APIRouter(prefix="/analysis", tags=["analysis"])

# 全局存储导出任务状态 (生产环境建议使用 Redis)
export_tasks = {}

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

@router.post("/lot/{lot_id}/export_items/start")
def start_export_test_items(
    lot_id: int,
    background_tasks: BackgroundTasks,
    filter_type: str = Query("all"),
    sigma: float = Query(3.0),
    data_range: str = Query("final"),
    chars_row: int = Query(3),
    selected_items: str = Query(""),
    db: Session = Depends(get_db),
):
    """启动异步导出任务"""
    task_id = str(uuid.uuid4())
    export_tasks[task_id] = {
        "status": "processing",
        "progress": 0,
        "result": None,
        "filename": f"LOT_{lot_id}_FullReport_{filter_type}.xlsx",
        "created_at": time.time()
    }
    
    background_tasks.add_task(
        run_export_task,
        task_id, lot_id, filter_type, sigma, data_range, chars_row, selected_items, db
    )
    
    return {"task_id": task_id}

@router.get("/export_items/status/{task_id}")
def get_export_status(task_id: str):
    """查询导出任务进度"""
    if task_id not in export_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = export_tasks[task_id]
    return {
        "status": task["status"],
        "progress": task["progress"],
        "error": task.get("error")
    }

@router.get("/export_items/download/{task_id}")
def download_export_result(task_id: str):
    """下载导出结果"""
    if task_id not in export_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = export_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    # 这里的 result 是 BytesIO 对象
    result = task["result"]
    result.seek(0)
    
    return StreamingResponse(
        result,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={task['filename']}"}
    )

def run_export_task(
    task_id: str,
    lot_id: int,
    filter_type: str,
    sigma: float,
    data_range: str,
    chars_row: int,
    selected_items: str,
    db: Session
):
    """后台执行导出任务"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import xlsxwriter
        import pandas as pd
        import io
        import numpy as np

        export_tasks[task_id]["progress"] = 5
        
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            export_tasks[task_id].update({"status": "failed", "error": "LOT不存在"})
            return

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

        export_tasks[task_id]["progress"] = 10

        # 预读数据
        df_all = pd.read_parquet(lot.parquet_path)
        if 'X_COORD' in df_all.columns and 'Y_COORD' in df_all.columns:
            if data_range == 'final':
                df_all = df_all.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')
            elif data_range == 'original':
                df_all = df_all.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='first')

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # ─── Sheet 1: Stats & Info ───
            stats_sheet = workbook.add_worksheet('Stats')
            
            # 定义格式
            info_label_fmt = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2', 'align': 'left'})
            info_val_fmt = workbook.add_format({'border': 1, 'align': 'left'})
            
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
                stats_sheet.write(row, 0, label, info_label_fmt)
                stats_sheet.write(row, 1, str(val) if val is not None else "", info_val_fmt)
                row += 1
            
            row += 2 # 空两行
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
                if 'Fail Rate' in df_stats.columns:
                    df_stats['Fail Rate'] = df_stats['Fail Rate'].apply(lambda x: float(x) if pd.notna(x) else 0.0)
                if 'Yield' in df_stats.columns:
                    df_stats['Yield'] = df_stats['Yield'].apply(lambda x: float(x) if pd.notna(x) else None)

                
                # 写入参数统计表并应用格式
                start_stats_row = row
                num_rows = len(df_stats)
                num_cols = len(df_stats.columns)
                
                for r_idx in range(num_rows + 1): # +1 为表头
                    for c_idx in range(num_cols):
                        is_header = (r_idx == 0)
                        col_name = df_stats.columns[c_idx]
                        is_test_item = (col_name == 'TestItem')
                        
                        fmt_props = {'border': 1, 'valign': 'vcenter'}
                        
                        # 粗外侧框线
                        if r_idx == 0: fmt_props['top'] = 2
                        if r_idx == num_rows: fmt_props['bottom'] = 2
                        if c_idx == 0: fmt_props['left'] = 2
                        if c_idx == num_cols - 1: fmt_props['right'] = 2
                        
                        if is_header:
                            fmt_props.update({'bold': True, 'align': 'center', 'bg_color': '#D9D9D9'})
                            val = col_name
                        else:
                            fmt_props['align'] = 'left' if is_test_item else 'center'
                            val = df_stats.iloc[r_idx - 1, c_idx]
                            if pd.isna(val): val = ""
                            if col_name in ['Fail Rate', 'Yield'] and isinstance(val, (int, float)):
                                fmt_props['num_format'] = '0.00%'
                            
                            # CPK/CPU/CPL 染色逻辑
                            if col_name in ['CPU', 'CPL', 'CPK'] and isinstance(val, (int, float)):
                                if val < 1.0:
                                    fmt_props.update({'font_color': 'red', 'bold': True})
                                elif val < 1.33:
                                    fmt_props.update({'font_color': '#FF8C00'}) # Orange

                        
                        cell_fmt = workbook.add_format(fmt_props)
                        stats_sheet.write(start_stats_row + r_idx, c_idx, val, cell_fmt)

                
                # 设置列宽
                stats_sheet.set_column(0, 0, 8)   # #
                stats_sheet.set_column(1, 1, 40)  # TestItem 40宽
                if num_cols > 2:
                    stats_sheet.set_column(2, num_cols - 1, 12) # 其余居中


            export_tasks[task_id]["progress"] = 15

            # ─── Sheet 2: Histograms ───
            hist_sheet = workbook.add_worksheet('Histograms')
            hist_sheet.set_column(0, 0, 10)
            hist_sheet.set_column(1, 1, 30)
            hist_sheet.set_column(2, 50, 10)
            
            header_format = workbook.add_format({'bold': True, 'font_color': 'blue'})
            hist_sheet.write(0, 2, "Data:", header_format)
            hist_sheet.write(0, 3, lot.filename, header_format)
            hist_sheet.write(1, 2, "Wafer:", header_format)
            hist_sheet.write(1, 3, lot.wafer_id, header_format)
            
            from app.services.stats import apply_filter, calc_param_stats, calc_hist_edges, calc_hist_x_range
            
            def draw_stats_line(ax_obj, y_pos, items_list):
                # 拼接统计信息为单行，用3个空格分隔
                line_text = "   ".join([f"{k}{v}" for k, v in items_list])
                ax_obj.text(0.5, y_pos, line_text, transform=ax_obj.transAxes, 
                            color='#000000', fontweight='bold', fontsize=8, ha='center')

            fig, ax = plt.subplots(figsize=(5.47, 4.5)) 
            SITE_COLORS = ['#ff6b6b', '#4dabf7', '#69db7c', '#ffd43b', '#e599f7', '#74c0fc', '#a9e34b', '#ffa94d']
            
            total_items = len(items_summary)
            for i, item in enumerate(items_summary):
                # 更新进度: 15% -> 80%
                current_progress = 15 + int((i / total_items) * 65) if total_items > 0 else 15
                export_tasks[task_id]["progress"] = current_progress

                p_name = item['item_name']
                p_num = item['item_number']
                if p_name not in df_all.columns: continue
                
                ll, ul = item.get('lower_limit'), item.get('upper_limit')
                unit = item.get('unit') or ''
                vals = df_all[p_name].dropna().values.astype(float)
                if len(vals) == 0: continue
                filtered_all = apply_filter(vals, filter_type, ll, ul, sigma)
                if len(filtered_all) == 0: continue
                edges, exceeds_limit, ll_bin_idx, ul_bin_idx = calc_hist_edges(filtered_all, ll, ul)
                
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
                s0_stats = calc_param_stats(filtered_all, ll, ul, len(filtered_all))
                data_min, data_max = float(np.min(filtered_all)), float(np.max(filtered_all))
                edges_min, edges_max = float(edges[0]), float(edges[-1])
                x_range_info = calc_hist_x_range(data_min, data_max, ll, ul, edges_min, edges_max)
                x_min, x_max = x_range_info['x_min'], x_range_info['x_max']
                
                if exceeds_limit:
                    max_count = np.max([np.max(s['counts']) for s in sites_data]) if sites_data else 1
                    min_h = max_count * 0.02
                    outlier_h = max_count * 0.05
                    for idx, s in enumerate(sites_data):
                        color = SITE_COLORS[idx % len(SITE_COLORS)]
                        sigma_l = s0_stats['mean'] - 6 * s0_stats['stdev'] if s0_stats.get('mean') is not None and s0_stats.get('stdev') is not None else None
                        sigma_u = s0_stats['mean'] + 6 * s0_stats['stdev'] if s0_stats.get('mean') is not None and s0_stats.get('stdev') is not None else None
                        final_normal, final_outlier = [], []
                        for i_bin, cnt in enumerate(s['counts']):
                            center = (edges[i_bin] + edges[i_bin+1]) / 2
                            is_outlier_type = sigma_l is not None and (center < sigma_l or center > sigma_u) and 0 < cnt < 5
                            if is_outlier_type:
                                final_normal.append(0); final_outlier.append(max(cnt, outlier_h))
                            elif cnt > 0:
                                val = max(cnt, min_h) if cnt < 5 else cnt
                                final_normal.append(val); final_outlier.append(0)
                            else:
                                final_normal.append(0); final_outlier.append(0)
                        bar_w = 0.9
                        ax.bar(range(len(final_normal)), final_normal, width=bar_w, alpha=0.7, color=color, label=f"Site{s['site']}", zorder=3)
                        if any(v > 0 for v in final_outlier):
                            ax.bar(range(len(final_outlier)), final_outlier, width=bar_w, alpha=0.8, color=color, zorder=4)
                    if ll_bin_idx is not None:
                        ax.axvline(ll_bin_idx, color='red', linestyle='--', linewidth=1.5, zorder=4)
                        ax.text(ll_bin_idx, ax.get_ylim()[1]*0.5, f'LL:{ll}', color='red', fontsize=7, ha='left', va='center', rotation=90)
                    if ul_bin_idx is not None:
                        ax.axvline(ul_bin_idx, color='red', linestyle='--', linewidth=1.5, zorder=4)
                        ax.text(ul_bin_idx, ax.get_ylim()[1]*0.5, f'UL:{ul}', color='red', fontsize=7, ha='right', va='center', rotation=90)
                    tick_indices = np.linspace(0, len(edges)-2, 11).astype(int)
                    ax.set_xticks(tick_indices)
                    ax.set_xticklabels([f"{edges[t]:.3f}" for t in tick_indices], rotation=30)
                else:
                    bin_centers = (edges[:-1] + edges[1:]) / 2
                    bin_w = edges[1] - edges[0] if len(edges) > 1 else 1
                    max_count = np.max([np.max(s['counts']) for s in sites_data]) if sites_data else 1
                    min_h = max_count * 0.02
                    outlier_h = max_count * 0.05
                    for idx, s in enumerate(sites_data):
                        color = SITE_COLORS[idx % len(SITE_COLORS)]
                        sigma_l = s0_stats['mean'] - 6 * s0_stats['stdev'] if s0_stats.get('mean') is not None and s0_stats.get('stdev') is not None else None
                        sigma_u = s0_stats['mean'] + 6 * s0_stats['stdev'] if s0_stats.get('mean') is not None and s0_stats.get('stdev') is not None else None
                        final_normal, final_outlier = [], []
                        for i_bin, cnt in enumerate(s['counts']):
                            center = (edges[i_bin] + edges[i_bin+1]) / 2
                            is_outlier_type = sigma_l is not None and (center < sigma_l or center > sigma_u) and 0 < cnt < 5
                            if is_outlier_type:
                                final_normal.append(0); final_outlier.append(max(cnt, outlier_h))
                            elif cnt > 0:
                                val = max(cnt, min_h) if cnt < 5 else cnt
                                final_normal.append(val); final_outlier.append(0)
                            else:
                                final_normal.append(0); final_outlier.append(0)
                        bar_w = max(bin_w * 0.9, (x_max - x_min) * 0.015)
                        ax.bar(bin_centers, final_normal, width=bar_w, alpha=0.7, color=color, label=f"Site{s['site']}", zorder=3)
                        if any(v > 0 for v in final_outlier):
                            ax.bar(bin_centers, final_outlier, width=bar_w, alpha=0.8, color=color, zorder=4)
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
                
                ax.set_title(f"{p_num}.{p_name}", fontsize=12, fontweight='bold', color='black', pad=32)
                cpk_val = s0_stats['cpk'] if s0_stats['cpk'] is not None else 0
                stats_info = [
                    ("Min=", f"{s0_stats['min_val']:.4f}"), 
                    ("Max=", f"{s0_stats['max_val']:.4f}"),
                    ("Mean=", f"{s0_stats['mean']:.4f}"), 
                    ("Stdev=", f"{s0_stats['stdev']:.4f}"), 
                    ("CPK=", f"{cpk_val:.4f}")
                ]
                draw_stats_line(ax, 1.03, stats_info)
                ax.set_ylabel("Parts", fontsize=8)
                ax.set_xlabel(unit, fontsize=12, fontweight='bold', color='black')
                ax.tick_params(labelsize=7)
                ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.22), ncol=4, fontsize=7, frameon=False)
                fig.tight_layout()
                img_data = io.BytesIO()
                plt.savefig(img_data, format='png', dpi=100)
                img_data.seek(0)
                
                group_idx = i // chars_row
                within_group_idx = i % chars_row
                r_idx = group_idx * 22 + 2
                c_idx = within_group_idx * 7 + 2
                info_r_idx = group_idx * 22 + 6 + within_group_idx
                hist_sheet.write(info_r_idx, 0, p_num)
                hist_sheet.write(info_r_idx, 1, p_name)
                hist_sheet.insert_image(r_idx, c_idx, f'h_{i}.png', {'image_data': img_data, 'x_scale': 1.0, 'y_scale': 1.0})

            plt.close(fig)
            export_tasks[task_id]["progress"] = 80

            # ─── Sheet 3: Bin Info & Map ───
            bin_sheet = workbook.add_worksheet('BinInfo')
            
            # 表头信息格式 (Lot Info)
            info_label_fmt = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2', 'align': 'left'})
            info_val_fmt = workbook.add_format({'border': 1, 'align': 'left'})

            info_row = 0
            bin_sheet.write_row(info_row, 0, ['Lot Information', ''], workbook.add_format({'bold': True, 'font_size': 12}))
            info_row += 1
            for key, label in info_labels.items():
                val = lot_info.get(key)
                if key == 'yield_rate' and val is not None: val = f"{val*100:.2f}%"
                bin_sheet.write(info_row, 0, label, info_label_fmt)
                bin_sheet.write(info_row, 1, str(val) if val is not None else "", info_val_fmt)
                info_row += 1
            
            pass_bins = _get_pass_bins(lot_id, db)
            row = info_row + 1
            sites = bin_data['sites']
            headers = ['Bin', 'Name'] + [f'Site{s}' for s in sites] + ['All Site', '% of total', 'Comment']
            
            # 辅助计算汇总行
            def get_site_pass(s): return sum(b['sites'].get(f'site{s}', {}).get('count', 0) for b in bin_data['bins'] if b['bin_number'] in pass_bins)
            def get_site_fail(s): return sum(b['sites'].get(f'site{s}', {}).get('count', 0) for b in bin_data['bins'] if b['bin_number'] not in pass_bins)
            def get_site_total(s): return sum(b['sites'].get(f'site{s}', {}).get('count', 0) for b in bin_data['bins'])
            total_pass = sum(b['all_site_count'] for b in bin_data['bins'] if b['bin_number'] in pass_bins)
            total_fail = sum(b['all_site_count'] for b in bin_data['bins'] if b['bin_number'] not in pass_bins)
            total_all = sum(b['all_site_count'] for b in bin_data['bins'])

            # 准备 Bin 表格数据
            bin_table_rows = []
            for b in bin_data['bins']:
                is_pass = b['bin_number'] in pass_bins
                r_data = [b['bin_number'], b['bin_name']]
                for s in sites: r_data.append(b['sites'].get(f'site{s}', {}).get('count', 0))
                r_data.extend([b['all_site_count'], (b.get('all_site_pct') or 0.0) / 100.0, b.get('comment', '')])
                bin_table_rows.append({'data': r_data, 'is_pass': is_pass, 'is_summary': False})

            
            bin_table_rows.append({'data': ['Passes', ''] + [get_site_pass(s) for s in sites] + [total_pass, total_pass/total_all if total_all > 0 else 0.0, ''], 'is_pass': True, 'is_summary': True})
            bin_table_rows.append({'data': ['Fails', ''] + [get_site_fail(s) for s in sites] + [total_fail, total_fail/total_all if total_all > 0 else 0.0, ''], 'is_pass': False, 'is_summary': True})
            bin_table_rows.append({'data': ['Sum', ''] + [get_site_total(s) for s in sites] + [total_all, 1.0, ''], 'is_pass': False, 'is_summary': True})


            # 写入 Bin 表格并应用格式
            start_bin_row = row
            num_bin_rows = len(bin_table_rows)
            num_bin_cols = len(headers)
            
            for r_idx in range(num_bin_rows + 1):
                for c_idx in range(num_bin_cols):
                    is_header = (r_idx == 0)
                    fmt_props = {'border': 1, 'valign': 'vcenter'}
                    
                    # 粗外侧框线
                    if r_idx == 0: fmt_props['top'] = 2
                    if r_idx == num_bin_rows: fmt_props['bottom'] = 2
                    if c_idx == 0: fmt_props['left'] = 2
                    if c_idx == num_bin_cols - 1: fmt_props['right'] = 2
                    
                    if is_header:
                        fmt_props.update({'bold': True, 'align': 'center', 'bg_color': '#D9D9D9'})
                        val = headers[c_idx]
                    else:
                        row_info = bin_table_rows[r_idx - 1]
                        val = row_info['data'][c_idx]
                        if row_info['is_summary']:
                            fmt_props.update({'bold': True, 'bg_color': '#FAFAFA', 'align': 'center'})
                        else:
                            if row_info['is_pass']: fmt_props['bg_color'] = '#E6FFE6'
                            fmt_props['align'] = 'left' if c_idx == 1 else 'center'
                        
                        # 无论是数据行还是汇总行，百分比列都应用格式
                        if headers[c_idx] == '% of total' and isinstance(val, (int, float)):
                            fmt_props['num_format'] = '0.00%'

                    
                    cell_fmt = workbook.add_format(fmt_props)
                    bin_sheet.write(start_bin_row + r_idx, c_idx, val, cell_fmt)

            
            row = start_bin_row + num_bin_rows + 1
            bin_sheet.set_column(0, len(headers)-1, 12)
            bin_sheet.set_column(1, 1, 25) # Name 列宽些，靠左
            bin_sheet.set_column(len(headers)-1, len(headers)-1, 20) # Comment 列

            
            export_tasks[task_id]["progress"] = 85

            row += 2
            if map_result['has_map'] and map_result['data']:
                import math
                import matplotlib.patches as patches
                from matplotlib.collections import PatchCollection
                from matplotlib.lines import Line2D
                df_map = pd.DataFrame(map_result['data'])
                effective_pass_bins = set(pass_bins) | {1, 2}
                primary_pass_bin = 1
                df_map['bin'] = df_map['bin'].apply(lambda b: primary_pass_bin if int(b) in effective_pass_bins else int(b))
                bin_counts = df_map['bin'].value_counts()
                FAIL_COLORS = ['#ff6b6b', '#4dabf7', '#ffd43b', '#e599f7', '#74c0fc', '#ffa94d', '#da77f2', '#ff8787', '#339af0', '#fcc419', '#cc5de8', '#22b8cf', '#ff922b', '#845ef7', '#f06595', '#66d9e8']
                BIN_COLORS = {}
                for b_num in df_map['bin'].values:
                    b_num = int(b_num)
                    if b_num not in BIN_COLORS:
                        if b_num in effective_pass_bins: BIN_COLORS[b_num] = '#69db7c'
                        else:
                            fail_count = sum(1 for v in BIN_COLORS.values() if v != '#69db7c')
                            BIN_COLORS[b_num] = FAIL_COLORS[fail_count % len(FAIL_COLORS)]
                n_bins = len(BIN_COLORS)
                # 放大 Map 图表尺寸
                fig, ax = plt.subplots(figsize=(10 + max(0, n_bins*0.05), 8 + max(0, n_bins*0.1)))
                xs, ys, bins = df_map['x'].values, df_map['y'].values, df_map['bin'].values
                rects = [patches.Rectangle((x - 0.5, y - 0.5), 1, 1) for x, y in zip(xs, ys)]
                colors = [BIN_COLORS.get(int(b), '#000000') for b in bins]
                pc = PatchCollection(rects, facecolors=colors, edgecolors='white', linewidths=0.5)
                ax.add_collection(pc)
                if 'retest' in df_map.columns:
                    retest_df = df_map[df_map['retest'] == True]
                    crosses = []
                    for _, r in retest_df.iterrows():
                        x, y = r['x'], r['y']; arm, thick = 0.3, 0.15
                        crosses.append(patches.Rectangle((x - thick/2, y - arm), thick, arm*2))
                        crosses.append(patches.Rectangle((x - arm, y - thick/2), arm*2, thick))
                    if crosses:
                        pc_cross = PatchCollection(crosses, facecolors=(0, 0, 0, 0.2), edgecolors='none')
                        ax.add_collection(pc_cross)
                min_x, max_x = int(df_map['x'].min()), int(df_map['x'].max())
                min_y, max_y = int(df_map['y'].min()), int(df_map['y'].max())
                ax.set_xlim(min_x - 1, max_x + 1)
                ax.set_ylim(max_y + 1, min_y - 1)
                ax.set_aspect('equal')
                ax.set_title('Wafer Bin Map', fontsize=14, pad=20, fontweight='bold')
                gridW, gridH = max_x - min_x + 1, max_y - min_y + 1
                x_step, y_step = max(1, int(math.ceil(gridW / 10.0))), max(1, int(math.ceil(gridH / 10.0)))
                ax.set_xticks(range(min_x, max_x + 1, x_step)); ax.set_yticks(range(min_y, max_y + 1, y_step))
                ax.xaxis.tick_top(); ax.yaxis.tick_left(); ax.tick_params(axis='both', which='both', length=0, labelsize=9, colors='#aaaaaa')
                for spine in ax.spines.values(): spine.set_visible(False)
                sorted_bins = sorted(BIN_COLORS.keys(), key=lambda x: (-bin_counts.get(x, 0), x))
                legend_elements = [Line2D([0], [0], marker='o', color='w', label=f'Bin{b} ({bin_counts.get(b, 0)})', markerfacecolor=BIN_COLORS[b], markersize=8, markeredgecolor='none') for b in sorted_bins]
                ax.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1.02, 0.5), frameon=False, labelcolor='#333333')
                
                img_data = io.BytesIO()
                plt.savefig(img_data, format='png', dpi=100, bbox_inches='tight')
                plt.close(fig)
                img_data.seek(0)
                bin_sheet.insert_image(row, 0, 'wafer_map.png', {'image_data': img_data, 'x_scale': 1.1, 'y_scale': 1.1})

            export_tasks[task_id]["progress"] = 95

        output.seek(0)
        export_tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "result": output
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        export_tasks[task_id].update({
            "status": "failed",
            "error": str(e)
        })

@router.get("/lot/{lot_id}/export_items_old")
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
        
        # 定义格式
        info_label_fmt = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2', 'align': 'left'})
        info_val_fmt = workbook.add_format({'border': 1, 'align': 'left'})
        
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
            stats_sheet.write(row, 0, label, info_label_fmt)
            stats_sheet.write(row, 1, str(val) if val is not None else "", info_val_fmt)
            row += 1
        
        row += 2 # 空两行
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
                df_stats['Fail Rate'] = df_stats['Fail Rate'].apply(lambda x: float(x) if pd.notna(x) else 0.0)
            if 'Yield' in df_stats.columns:
                df_stats['Yield'] = df_stats['Yield'].apply(lambda x: float(x) if pd.notna(x) else None)

            
            # 写入参数统计表并应用格式
            start_stats_row = row
            num_rows = len(df_stats)
            num_cols = len(df_stats.columns)
            
            for r_idx in range(num_rows + 1): # +1 为表头
                for c_idx in range(num_cols):
                    is_header = (r_idx == 0)
                    col_name = df_stats.columns[c_idx]
                    is_test_item = (col_name == 'TestItem')
                    
                    fmt_props = {'border': 1, 'valign': 'vcenter'}
                    
                    # 粗外侧框线
                    if r_idx == 0: fmt_props['top'] = 2
                    if r_idx == num_rows: fmt_props['bottom'] = 2
                    if c_idx == 0: fmt_props['left'] = 2
                    if c_idx == num_cols - 1: fmt_props['right'] = 2
                    
                    if is_header:
                        fmt_props.update({'bold': True, 'align': 'center', 'bg_color': '#D9D9D9'})
                        val = col_name
                    else:
                        fmt_props['align'] = 'left' if is_test_item else 'center'
                        val = df_stats.iloc[r_idx - 1, c_idx]
                        if pd.isna(val): val = ""
                        if col_name in ['Fail Rate', 'Yield'] and isinstance(val, (int, float)):
                            fmt_props['num_format'] = '0.00%'
                        
                        # CPK/CPU/CPL 染色逻辑
                        if col_name in ['CPU', 'CPL', 'CPK'] and isinstance(val, (int, float)):
                            if val < 1.0:
                                fmt_props.update({'font_color': 'red', 'bold': True})
                            elif val < 1.33:
                                fmt_props.update({'font_color': '#FF8C00'}) # Orange

                    
                    cell_fmt = workbook.add_format(fmt_props)
                    stats_sheet.write(start_stats_row + r_idx, c_idx, val, cell_fmt)

            
            # 设置列宽
            stats_sheet.set_column(0, 0, 8)   # #
            stats_sheet.set_column(1, 1, 40)  # TestItem 40宽
            if num_cols > 2:
                stats_sheet.set_column(2, num_cols - 1, 12) # 其余居中


        # ─── Sheet 2: Histograms ───
        hist_sheet = workbook.add_worksheet('Histograms')
        hist_sheet.set_column(0, 0, 10) # A列: 参数编号
        hist_sheet.set_column(1, 1, 30) # B列: 参数名
        hist_sheet.set_column(2, 50, 10) # 其余列宽
        
        # 写入顶部汇总信息
        header_format = workbook.add_format({'bold': True, 'font_color': 'blue'})
        hist_sheet.write(0, 2, "Data:", header_format) # C1
        hist_sheet.write(0, 3, lot.filename, header_format) # D1
        hist_sheet.write(1, 2, "Wafer:", header_format) # C2
        hist_sheet.write(1, 3, lot.wafer_id, header_format) # D2
        
        from app.services.stats import apply_filter, calc_param_stats, calc_hist_edges, calc_hist_x_range
        
        def draw_stats_line(ax_obj, y_pos, items_list):
            # 拼接统计信息为单行，用3个空格分隔
            line_text = "   ".join([f"{k}{v}" for k, v in items_list])
            ax_obj.text(0.5, y_pos, line_text, transform=ax_obj.transAxes, 
                        color='#00008B', fontweight='bold', fontsize=8, ha='center')

        # 复用 figure 以提升速度
        fig, ax = plt.subplots(figsize=(5.47, 4.5)) 
        SITE_COLORS = ['#ff6b6b', '#4dabf7', '#69db7c', '#ffd43b', '#e599f7', '#74c0fc', '#a9e34b', '#ffa94d']
        chars_row = 2 # 每行显示的图表数
        
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
                # 计算一个可见的最小高度 (例如最大计数的 2%)
                max_count = np.max([np.max(s['counts']) for s in sites_data]) if sites_data else 1
                min_h = max_count * 0.02
                # 异常点锁定高度 (例如最大计数的 5%，对应前端的 5-10px)
                outlier_h = max_count * 0.05

                for idx, s in enumerate(sites_data):
                    color = SITE_COLORS[idx % len(SITE_COLORS)]
                    
                    # 计算 sigma 区间
                    sigma_l = s0_stats['mean'] - 6 * s0_stats['stdev'] if s0_stats.get('mean') is not None and s0_stats.get('stdev') is not None else None
                    sigma_u = s0_stats['mean'] + 6 * s0_stats['stdev'] if s0_stats.get('mean') is not None and s0_stats.get('stdev') is not None else None
                    
                    final_normal = []
                    final_outlier = []
                    
                    for i_bin, cnt in enumerate(s['counts']):
                        center = (edges[i_bin] + edges[i_bin+1]) / 2
                        is_outlier_type = sigma_l is not None and (center < sigma_l or center > sigma_u) and 0 < cnt < 5
                        
                        if is_outlier_type:
                            final_normal.append(0)
                            final_outlier.append(max(cnt, outlier_h))
                        elif cnt > 0:
                            # 数量在 1-5 之间时使用最小高度 min_h
                            val = max(cnt, min_h) if cnt < 5 else cnt
                            final_normal.append(val)
                            final_outlier.append(0)
                        else:
                            final_normal.append(0)
                            final_outlier.append(0)
                    
                    # 绘制正常柱子 (强制最小宽度为 X轴范围的 1.5%，避免变成一根线)
                    bar_w = 0.9
                    ax.bar(x_pos, final_normal, width=bar_w, alpha=0.7, color=color, label=f"Site{s['site']}", zorder=3)
                    # 绘制异常柱子 (如果存在)
                    if any(v > 0 for v in final_outlier):
                        ax.bar(x_pos, final_outlier, width=bar_w, alpha=0.8, color=color, zorder=4)



                
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
                # 计算一个可见的最小高度
                max_count = np.max([np.max(s['counts']) for s in sites_data]) if sites_data else 1
                min_h = max_count * 0.02
                outlier_h = max_count * 0.05

                for idx, s in enumerate(sites_data):
                    color = SITE_COLORS[idx % len(SITE_COLORS)]
                    
                    # 计算 sigma 区间
                    sigma_l = s0_stats['mean'] - 6 * s0_stats['stdev'] if s0_stats.get('mean') is not None and s0_stats.get('stdev') is not None else None
                    sigma_u = s0_stats['mean'] + 6 * s0_stats['stdev'] if s0_stats.get('mean') is not None and s0_stats.get('stdev') is not None else None
                    
                    final_normal = []
                    final_outlier = []
                    
                    for i_bin, cnt in enumerate(s['counts']):
                        center = (edges[i_bin] + edges[i_bin+1]) / 2
                        is_outlier_type = sigma_l is not None and (center < sigma_l or center > sigma_u) and 0 < cnt < 5
                        
                        if is_outlier_type:
                            final_normal.append(0)
                            final_outlier.append(max(cnt, outlier_h))
                        elif cnt > 0:
                            val = max(cnt, min_h) if cnt < 5 else cnt
                            final_normal.append(val)
                            final_outlier.append(0)
                        else:
                            final_normal.append(0)
                            final_outlier.append(0)

                    # 强制最小宽度为 X轴范围的 1.5%，避免变成一根线
                    bar_w = max(bin_w * 0.9, (x_max - x_min) * 0.015)
                    
                    ax.bar(bin_centers, final_normal, width=bar_w, alpha=0.7, color=color, label=f"Site{s['site']}", zorder=3)
                    if any(v > 0 for v in final_outlier):
                        ax.bar(bin_centers, final_outlier, width=bar_w, alpha=0.8, color=color, zorder=4)



                
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
            
            # 1. 标题：参数名 (黑色加粗, 字体大1号)
            ax.set_title(f"{p_num}.{p_name}", fontsize=12, fontweight='bold', color='black', pad=32)

            # 2. 参数信息：所有统计信息合并为一行 (全部使用深蓝色加粗显示)
            cpk_val = s0_stats['cpk'] if s0_stats['cpk'] is not None else 0
            stats_info = [
                ("Min=", f"{s0_stats['min_val']:.4f}"), 
                ("Max=", f"{s0_stats['max_val']:.4f}"),
                ("Mean=", f"{s0_stats['mean']:.4f}"), 
                ("Stdev=", f"{s0_stats['stdev']:.4f}"), 
                ("CPK=", f"{cpk_val:.4f}")
            ]
            draw_stats_line(ax, 1.03, stats_info)
 
            ax.set_ylabel("Parts", fontsize=8)
            # 3. X轴单位：黑色加粗, 字体大1号
            ax.set_xlabel(unit, fontsize=12, fontweight='bold', color='black')
            ax.tick_params(labelsize=7)
            
            # 添加图例在下方
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.22), ncol=4, fontsize=7, frameon=False)
            
            fig.tight_layout()
            img_data = io.BytesIO()
            plt.savefig(img_data, format='png', dpi=100)
            img_data.seek(0)
            
            # 计算位置
            group_idx = i // chars_row
            within_group_idx = i % chars_row
            r_idx = group_idx * 22 + 2
            c_idx = within_group_idx * 7 + 2
            
            # 写入参数信息在左侧 (第一列 and 第二列)，随图表分组换行
            info_r_idx = group_idx * 22 + 6 + within_group_idx
            hist_sheet.write(info_r_idx, 0, p_num)
            hist_sheet.write(info_r_idx, 1, p_name)
            
            hist_sheet.insert_image(r_idx, c_idx, 
            f'h_{i}.png', {
                'image_data': img_data,
                'x_scale': 1.0,
                'y_scale': 1.0
            })
        plt.close(fig) # 循环结束后关闭

        # ─── Sheet 3: Bin Info & Map ───
        bin_sheet = workbook.add_worksheet('BinInfo')
        
        # 定义样式 (Lot Info)
        info_label_fmt = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2', 'align': 'left'})
        info_val_fmt = workbook.add_format({'border': 1, 'align': 'left'})

        # 表头信息 (Lot Info)
        info_row = 0
        bin_sheet.write_row(info_row, 0, ['Lot Information', ''], workbook.add_format({'bold': True, 'font_size': 12}))
        info_row += 1
        for key, label in info_labels.items():
            val = lot_info.get(key)
            if key == 'yield_rate' and val is not None:
                val = f"{val*100:.2f}%"
            bin_sheet.write(info_row, 0, label, info_label_fmt)
            bin_sheet.write(info_row, 1, str(val) if val is not None else "", info_val_fmt)
            info_row += 1
        
        # 获取 Pass Bins
        pass_bins = _get_pass_bins(lot_id, db)
        
        # Bin 表格
        row = info_row + 1
        sites = bin_data['sites']
        headers = ['Bin', 'Name'] + [f'Site{s}' for s in sites] + ['All Site', '% of total', 'Comment']
        
        # 辅助计算函数
        def get_site_pass(s): return sum(b['sites'].get(f'site{s}', {}).get('count', 0) for b in bin_data['bins'] if b['bin_number'] in pass_bins)
        def get_site_fail(s): return sum(b['sites'].get(f'site{s}', {}).get('count', 0) for b in bin_data['bins'] if b['bin_number'] not in pass_bins)
        def get_site_total(s): return sum(b['sites'].get(f'site{s}', {}).get('count', 0) for b in bin_data['bins'])
        
        total_pass = sum(b['all_site_count'] for b in bin_data['bins'] if b['bin_number'] in pass_bins)
        total_fail = sum(b['all_site_count'] for b in bin_data['bins'] if b['bin_number'] not in pass_bins)
        total_all = sum(b['all_site_count'] for b in bin_data['bins'])

        # 准备数据
        bin_table_rows = []
        for b in bin_data['bins']:
            is_pass = b['bin_number'] in pass_bins
            r_data = [b['bin_number'], b['bin_name']]
            for s in sites: r_data.append(b['sites'].get(f'site{s}', {}).get('count', 0))
            r_data.extend([b['all_site_count'], (b.get('all_site_pct') or 0.0) / 100.0, b.get('comment', '')])
            bin_table_rows.append({'data': r_data, 'is_pass': is_pass, 'is_summary': False})

        
        bin_table_rows.append({'data': ['Passes', ''] + [get_site_pass(s) for s in sites] + [total_pass, total_pass/total_all if total_all > 0 else 0.0, ''], 'is_pass': True, 'is_summary': True})
        bin_table_rows.append({'data': ['Fails', ''] + [get_site_fail(s) for s in sites] + [total_fail, total_fail/total_all if total_all > 0 else 0.0, ''], 'is_pass': False, 'is_summary': True})
        bin_table_rows.append({'data': ['Sum', ''] + [get_site_total(s) for s in sites] + [total_all, 1.0, ''], 'is_pass': False, 'is_summary': True})


        # 写入 Bin 表格
        start_bin_row = row
        num_bin_rows = len(bin_table_rows)
        num_bin_cols = len(headers)
        
        for r_idx in range(num_bin_rows + 1):
            for c_idx in range(num_bin_cols):
                is_header = (r_idx == 0)
                fmt_props = {'border': 1, 'valign': 'vcenter'}
                
                if r_idx == 0: fmt_props['top'] = 2
                if r_idx == num_bin_rows: fmt_props['bottom'] = 2
                if c_idx == 0: fmt_props['left'] = 2
                if c_idx == num_bin_cols - 1: fmt_props['right'] = 2
                
                if is_header:
                    fmt_props.update({'bold': True, 'align': 'center', 'bg_color': '#D9D9D9'})
                    val = headers[c_idx]
                else:
                    row_info = bin_table_rows[r_idx - 1]
                    val = row_info['data'][c_idx]
                    if row_info['is_summary']:
                        fmt_props.update({'bold': True, 'bg_color': '#FAFAFA', 'align': 'center'})
                    else:
                        if row_info['is_pass']: fmt_props['bg_color'] = '#E6FFE6'
                        fmt_props['align'] = 'left' if c_idx == 1 else 'center'
                    
                    if headers[c_idx] == '% of total' and isinstance(val, (int, float)):
                        fmt_props['num_format'] = '0.00%'

                
                cell_fmt = workbook.add_format(fmt_props)
                bin_sheet.write(start_bin_row + r_idx, c_idx, val, cell_fmt)

        
        row = start_bin_row + num_bin_rows + 1
        bin_sheet.set_column(0, len(headers)-1, 12)
        bin_sheet.set_column(1, 1, 25) # Name 列宽些，靠左
        bin_sheet.set_column(len(headers)-1, len(headers)-1, 20) # Comment 列

        
        # Wafer Map
        row += 2
        if map_result['has_map'] and map_result['data']:
            import math
            import matplotlib.patches as patches
            from matplotlib.collections import PatchCollection
            from matplotlib.lines import Line2D
            
            df_map = pd.DataFrame(map_result['data'])
            
            # 隐藏逻辑: Bin 1 和 Bin 2 都认为是良品。最终合在一起显示为 Bin 1
            effective_pass_bins = set(pass_bins) | {1, 2}
            primary_pass_bin = 1
            df_map['bin'] = df_map['bin'].apply(lambda b: primary_pass_bin if int(b) in effective_pass_bins else int(b))
                
            bin_counts = df_map['bin'].value_counts()
            
            # 完全复刻前端颜色的生成逻辑：按数据顺序首次遇到则分配颜色
            FAIL_COLORS = ['#ff6b6b', '#4dabf7', '#ffd43b', '#e599f7', '#74c0fc', '#ffa94d', '#da77f2', '#ff8787', '#339af0', '#fcc419', '#cc5de8', '#22b8cf', '#ff922b', '#845ef7', '#f06595', '#66d9e8']
            BIN_COLORS = {}
            for b_num in df_map['bin'].values:
                b_num = int(b_num)
                if b_num not in BIN_COLORS:
                    if b_num in effective_pass_bins:
                        BIN_COLORS[b_num] = '#69db7c'
                    else:
                        fail_count = sum(1 for v in BIN_COLORS.values() if v != '#69db7c')
                        BIN_COLORS[b_num] = FAIL_COLORS[fail_count % len(FAIL_COLORS)]
            
            n_bins = len(BIN_COLORS)
            # 放大 Map 图表尺寸
            fig, ax = plt.subplots(figsize=(10 + max(0, n_bins*0.05), 8 + max(0, n_bins*0.1)))
            
            xs = df_map['x'].values
            ys = df_map['y'].values
            bins = df_map['bin'].values
            
            # 使用 PatchCollection 绘制方块阵列（白边线达到前端Grid效果）
            rects = [patches.Rectangle((x - 0.5, y - 0.5), 1, 1) for x, y in zip(xs, ys)]
            colors = [BIN_COLORS.get(int(b), '#000000') for b in bins]
            
            pc = PatchCollection(rects, facecolors=colors, edgecolors='white', linewidths=0.5)
            ax.add_collection(pc)
            
            # 复刻前端的复测标记 (黑色半透明十字)
            if 'retest' in df_map.columns:
                retest_df = df_map[df_map['retest'] == True]
                crosses = []
                for _, r in retest_df.iterrows():
                    x, y = r['x'], r['y']
                    arm = 0.3
                    thick = 0.15
                    crosses.append(patches.Rectangle((x - thick/2, y - arm), thick, arm*2))
                    crosses.append(patches.Rectangle((x - arm, y - thick/2), arm*2, thick))
                if crosses:
                    pc_cross = PatchCollection(crosses, facecolors=(0, 0, 0, 0.2), edgecolors='none')
                    ax.add_collection(pc_cross)
            
            min_x, max_x = int(df_map['x'].min()), int(df_map['x'].max())
            min_y, max_y = int(df_map['y'].min()), int(df_map['y'].max())
            
            ax.set_xlim(min_x - 1, max_x + 1)
            ax.set_ylim(max_y + 1, min_y - 1)  # Invert Y
            ax.set_aspect('equal')
            ax.set_title('Wafer Bin Map', fontsize=14, pad=20, fontweight='bold')
            
            # 刻度标记逻辑复刻前端
            gridW = max_x - min_x + 1
            gridH = max_y - min_y + 1
            x_step = max(1, int(math.ceil(gridW / 10.0)))
            y_step = max(1, int(math.ceil(gridH / 10.0)))
            
            ax.set_xticks(range(min_x, max_x + 1, x_step))
            ax.set_yticks(range(min_y, max_y + 1, y_step))
            
            # 刻度放在上边和左侧
            ax.xaxis.tick_top()
            ax.yaxis.tick_left()
            ax.tick_params(axis='both', which='both', length=0, labelsize=9, colors='#aaaaaa')
            
            # 隐藏外边框
            for spine in ax.spines.values():
                spine.set_visible(False)
            
            # 图例排序：按前端 Fail Bins 数量降序逻辑，但把 Pass Bins 放在最前或按原顺序
            # 前端展示时，Legend顺序是 All, 然后 Fail Bins 降序。这里按 count 降序。
            sorted_bins = sorted(BIN_COLORS.keys(), key=lambda x: (-bin_counts.get(x, 0), x))
            legend_elements = [
                Line2D([0], [0], marker='o', color='w', label=f'Bin{b} ({bin_counts.get(b, 0)})',
                       markerfacecolor=BIN_COLORS[b], markersize=8, markeredgecolor='none')
                for b in sorted_bins
            ]
            ax.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1.02, 0.5), frameon=False, labelcolor='#333333')
            
            img_data = io.BytesIO()
            plt.savefig(img_data, format='png', dpi=100, bbox_inches='tight')
            plt.close(fig)
            img_data.seek(0)
            bin_sheet.insert_image(row, 0, 'wafer_map.png', {'image_data': img_data, 'x_scale': 1.1, 'y_scale': 1.1})

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
    custom_ll: Optional[float] = Query(None),
    custom_ul: Optional[float] = Query(None),
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

    if filter_type == 'custom':
        if custom_ll is not None:
            ll = custom_ll
        if custom_ul is not None:
            ul = custom_ul

    # 应用Filter
    from app.services.stats import apply_filter, calc_param_stats

    result_data = []

    # ── 先计算 All Sites (site=0) ─────────────────────────
    all_values = df[param_name].dropna().values.astype(float)
    if filter_type == 'filter_by_sigma' and len(all_values) > 1:
        mean_val = np.mean(all_values)
        std_val = np.std(all_values, ddof=1)
        ll = float(mean_val - sigma * std_val)
        ul = float(mean_val + sigma * std_val)

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
    custom_ll: Optional[float] = Query(None),
    custom_ul: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    """
    多LOT单参数直方图数据，各LOT共用同一套 global_edges
    """
    from app.services.stats import apply_filter, calc_param_stats, calc_hist_edges

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

    if filter_type == 'custom':
        if custom_ll is not None:
            ll = custom_ll
        if custom_ul is not None:
            ul = custom_ul

    # 先收集所有LOT的全部数据，计算全局 edges
    all_raw_combined = []
    lot_raw_values: dict = {}
    for lot in ordered_lots:
        if not lot.parquet_path or not os.path.exists(lot.parquet_path):
            lot_raw_values[lot.id] = np.array([])
            continue
        df = pd.read_parquet(lot.parquet_path)
        if param_name not in df.columns:
            lot_raw_values[lot.id] = np.array([])
            continue
        if 'X_COORD' in df.columns and 'Y_COORD' in df.columns:
            if data_range == 'final':
                df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='last')
            elif data_range == 'original':
                df = df.drop_duplicates(subset=['X_COORD', 'Y_COORD'], keep='first')
        vals = df[param_name].dropna().values.astype(float)
        lot_raw_values[lot.id] = vals
        all_raw_combined.extend(vals.tolist())

    all_raw_arr = np.array(all_raw_combined)

    if filter_type == 'filter_by_sigma' and len(all_raw_arr) > 1:
        mean_val = np.mean(all_raw_arr)
        std_val = np.std(all_raw_arr, ddof=1)
        ll = float(mean_val - sigma * std_val)
        ul = float(mean_val + sigma * std_val)

    all_values_combined = []
    lot_values: dict = {}
    for lot in ordered_lots:
        vals = lot_raw_values.get(lot.id, np.array([]))
        filtered = apply_filter(vals, filter_type, ll, ul, sigma, custom_min, custom_max)
        lot_values[lot.id] = filtered
        all_values_combined.extend(filtered.tolist())

    all_arr = np.array(all_values_combined)

    # 使用 calc_hist_edges 获得与 ParamView 一致的 exceeds_limit 逻辑
    if len(all_arr) > 1:
        global_edges, exceeds_limit, ll_bin_index, ul_bin_index = calc_hist_edges(all_arr, ll, ul)
    else:
        NUM_BINS = 50
        global_edges = np.linspace(0, 1, NUM_BINS + 1)
        exceeds_limit = False
        ll_bin_index = None
        ul_bin_index = None

    global_edges_list = [round(float(e), 6) for e in global_edges.tolist()]

    result = []
    for lot in ordered_lots:
        vals = lot_values.get(lot.id, np.array([]))
        if len(vals) > 0:
            counts, _ = np.histogram(vals, bins=global_edges)
            counts_list = counts.tolist()
        else:
            counts_list = [0] * (len(global_edges) - 1)
        stats = calc_param_stats(vals, ll, ul, len(vals)) if len(vals) > 0 else {}
        result.append({
            "lot_id": lot.id,
            "filename": lot.filename,
            "wafer_id": lot.wafer_id or "",
            "lot_id_str": lot.lot_id or "",
            "counts": counts_list,
            "stats": stats,
        })

    overall_stats = calc_param_stats(all_arr, ll, ul, len(all_arr)) if len(all_arr) > 0 else {}

    return {
        "param_name": param_name,
        "unit": unit,
        "lower_limit": ll,
        "upper_limit": ul,
        "global_edges": global_edges_list,
        "exceeds_limit": exceeds_limit,
        "ll_bin_index": ll_bin_index,
        "ul_bin_index": ul_bin_index,
        "lots": result,
        "overall_stats": overall_stats,
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
        "lots": [{"id": l.id, "filename": l.filename, "lot_id": l.lot_id, "wafer_id": l.wafer_id} for l in ordered_lots],
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
            "wafer_id": lot.wafer_id,
            "has_map": True,
            "data": tmp.to_dict('records'),
        })

    return {"maps": result}
