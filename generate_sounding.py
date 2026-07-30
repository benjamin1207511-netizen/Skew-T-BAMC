#!/usr/bin/env python3
"""
站点45004探空图生成脚本 - 多区域多日期智能尝试
"""

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import metpy.calc as mpcalc
from metpy.plots import SkewT
from metpy.units import units
from siphon.simplewebservice.wyoming import WyomingUpperAir
from datetime import datetime, timedelta
import os
import sys
import time
import traceback
import numpy as np

STATION = '45004'
OUTPUT_DIR = 'images'
OUTPUT_FILE = f'{OUTPUT_DIR}/sounding_{STATION}.png'
STATION_NAME = '香港'

# 候选区域列表（按优先级）
REGIONS = ['easia', 'asia', 'naconf']


def try_fetch_data(station, query_time, region):
    """尝试获取一次数据"""
    print(f"  尝试区域: {region}, 时间: {query_time.strftime('%Y-%m-%d %HZ')}")
    try:
        df = WyomingUpperAir.request_data(query_time, station, region=region)
        if df is not None and not df.empty:
            print(f"  ✅ 成功！共 {len(df)} 层")
            return df
        else:
            print(f"  ⚠️ 返回空数据")
            return None
    except Exception as e:
        print(f"  ❌ 失败: {str(e)[:60]}")
        return None


def get_latest_sounding(station):
    """智能获取最新数据"""
    now = datetime.utcnow()
    # 尝试两个施放时间：00Z 和 12Z
    candidate_times = []
    for hour in [0, 12]:
        t = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        # 如果当前时间早于该施放时间，则取前一天
        if now < t:
            t = t - timedelta(days=1)
        candidate_times.append(t)
    # 再加上前一天的 00Z 和 12Z 作为备选
    for t in candidate_times[:]:
        candidate_times.append(t - timedelta(days=1))
        candidate_times.append(t - timedelta(days=2))
    # 去重
    candidate_times = list(dict.fromkeys(candidate_times))

    print(f"📍 站点: {station} ({STATION_NAME})")
    print(f"🔍 将尝试 {len(candidate_times)} 个时间 x {len(REGIONS)} 个区域")

    for region in REGIONS:
        for dt in candidate_times:
            df = try_fetch_data(station, dt, region)
            if df is not None and not df.empty:
                print(f"🎯 最终使用: 区域={region}, 时间={dt.strftime('%Y-%m-%d %HZ')}")
                return df, dt
        print(f"  区域 {region} 所有时间均失败，切换到下一个区域...")

    # 所有尝试都失败
    print("❌ 所有区域和时间尝试均失败")
    return None, None


def generate_plot(df, station, output_path, query_time):
    """生成探空图"""
    print("⏳ 正在生成探空图...")

    # 如果数据为空，生成占位图
    if df is None or df.empty:
        print("⚠️ 无有效数据，生成占位图")
        fig = plt.figure(figsize=(10, 12), facecolor='white')
        plt.text(0.5, 0.5, '数据暂不可用\n请稍后重试',
                 ha='center', va='center', fontsize=20, color='gray')
        plt.axis('off')
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        plt.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"✅ 占位图已保存至: {output_path}")
        return

    # 正常绘制（原有代码，略作优化）
    try:
        p = df['pressure'].values * units.hPa
        T = df['temperature'].values * units.degC
        Td = df['dewpoint'].values * units.degC
        u = df['u_wind'].values * units.knot
        v = df['v_wind'].values * units.knot
    except KeyError as e:
        print(f"❌ 数据列缺失: {e}")
        raise

    valid_mask = (p.magnitude > 0) & (T.magnitude > -100) & (T.magnitude < 60) & (p.magnitude < 1100)
    if not all(valid_mask):
        p = p[valid_mask]; T = T[valid_mask]; Td = Td[valid_mask]; u = u[valid_mask]; v = v[valid_mask]

    if len(p) < 5:
        raise ValueError(f"有效数据点太少 ({len(p)})")

    # 去重
    df_filtered = df[valid_mask]
    df_unique = df_filtered.drop_duplicates(subset=['pressure'])
    if len(df_unique) < len(df_filtered):
        p = df_unique['pressure'].values * units.hPa
        T = df_unique['temperature'].values * units.degC
        Td = df_unique['dewpoint'].values * units.degC
        u = df_unique['u_wind'].values * units.knot
        v = df_unique['v_wind'].values * units.knot

    # 物理量
    try:
        parcel_profile = mpcalc.parcel_profile(p, T[0], Td[0])
        cape, cin = mpcalc.cape_cin(p, T, Td, parcel_profile)
        k_index = mpcalc.k_index(p, T, Td)
        lcl_p, lcl_t = mpcalc.lcl(p[0], T[0], Td[0])
    except Exception as e:
        print(f"⚠️ 物理量计算失败: {e}")
        parcel_profile = p * 0 + 273
        cape = cin = 0 * units('J/kg')
        k_index = 0 * units('degC')
        lcl_p, lcl_t = None, None

    # 绘图
    fig = plt.figure(figsize=(10, 12), dpi=120, facecolor='white')
    skew = SkewT(fig, rotation=35)
    skew.plot_dry_adiabats(linewidth=0.5, alpha=0.3, colors='#d4a574')
    skew.plot_moist_adiabats(linewidth=0.5, alpha=0.3, colors='#74a5d4')
    skew.plot_mixing_lines(linewidth=0.5, alpha=0.3, colors='#74d4a5')
    skew.plot(p, T, 'r', linewidth=2.5, label='温度层结')
    skew.plot(p, Td, 'g', linewidth=2.5, label='露点层结')
    skew.plot(p, parcel_profile, 'k', linewidth=2, linestyle='--', label='状态曲线')

    # LCL
    lcl_valid = False
    if lcl_p is not None and lcl_t is not None:
        try:
            if (hasattr(lcl_p, 'magnitude') and hasattr(lcl_t, 'magnitude') and
                not np.isnan(lcl_p.magnitude) and not np.isnan(lcl_t.magnitude) and
                lcl_p.magnitude > 0 and lcl_t.magnitude > -100 and lcl_p.magnitude < 1100):
                lcl_valid = True
        except:
            pass
    if lcl_valid:
        skew.plot(lcl_p, lcl_t, 'ko', markersize=12, label='LCL')
        skew.plot(lcl_p, lcl_t, 'yo', markersize=6)

    step = max(1, len(p) // 15)
    if step > 0:
        skew.plot_barbs(p[::step], u[::step], v[::step], xloc=1.08, length=5)

    skew.ax.set_ylim(1000, 100)
    skew.ax.set_xlim(-50, 50)
    skew.ax.set_ylabel('气压 (hPa)', fontsize=13, fontweight='bold')
    skew.ax.set_xlabel('温度 (°C)', fontsize=13, fontweight='bold')
    skew.ax.grid(True, linestyle='--', alpha=0.3)

    # 标题
    cape_val = cape.magnitude if hasattr(cape, 'magnitude') else 0
    cape_val = 0 if np.isnan(cape_val) else cape_val
    cape_str = f'{cape_val:.1f}' if cape_val < 9999 else '>9999'
    k_val = k_index.magnitude if hasattr(k_index, 'magnitude') else 0
    k_val = 0 if np.isnan(k_val) else k_val
    lcl_str = f'{lcl_p.magnitude:.0f}' if lcl_valid else 'N/A'

    title = f'站点 {station} ({STATION_NAME}) 探空图\n'
    title += f'时间: {query_time.strftime("%Y-%m-%d %H:00 UTC")}\n'
    title += f'CAPE: {cape_str} J/kg  |  K指数: {k_val:.1f} °C  |  LCL: {lcl_str} hPa'
    plt.title(title, fontsize=11, pad=15)
    plt.legend(loc='upper right', fontsize=9)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✅ 探空图已保存至: {output_path}")


def main():
    print("=" * 60)
    print(f"📍 站点 {STATION} ({STATION_NAME}) 探空图生成器")
    print(f"🕐 运行时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    df, query_time = get_latest_sounding(STATION)
    generate_plot(df, STATION, OUTPUT_FILE, query_time)
    print("=" * 60)
    print("🎉 完成！")


if __name__ == '__main__':
    main()