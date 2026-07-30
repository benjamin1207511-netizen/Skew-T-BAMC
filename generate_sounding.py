#!/usr/bin/env python3
"""
站点45004探空图生成脚本 - 使用 IGRA2 数据源
"""

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import metpy.calc as mpcalc
from metpy.plots import SkewT
from metpy.units import units
from siphon.simplewebservice.igra2 import IGRAUpperAir  # 🔥 改用 IGRA2
from datetime import datetime, timedelta
import os
import sys
import time
import traceback
import numpy as np
import pandas as pd

STATION = '45004'
# 🔥 IGRA2 站点 ID 格式：C + 国家代码(000) + 站点号
# 香港 45004 -> C000045004
IGRA_STATION = 'C000045004'
OUTPUT_DIR = 'images'
OUTPUT_FILE = f'{OUTPUT_DIR}/sounding_{STATION}.png'
STATION_NAME = '香港'


def try_fetch_igra2(station, year, month, day, hour):
    """尝试从 IGRA2 获取数据"""
    query_time = datetime(year, month, day, hour)
    print(f"  尝试 IGRA2: {query_time.strftime('%Y-%m-%d %HZ')}")
    try:
        # IGRA2 返回 (DataFrame, Header)
        df, header = IGRAUpperAir.request_data(query_time, station)
        if df is not None and not df.empty:
            print(f"  ✅ 成功！共 {len(df)} 层")
            return df, query_time
        else:
            print(f"  ⚠️ 返回空数据")
            return None, None
    except Exception as e:
        print(f"  ❌ 失败: {str(e)[:80]}")
        return None, None


def get_latest_sounding(station):
    """智能获取最新数据"""
    now = datetime.utcnow()
    print(f"📍 站点: {station} ({STATION_NAME})")
    print(f"🔍 使用 IGRA2 数据源")

    # 尝试最近 7 天的 00Z 和 12Z
    for days_ago in range(7):
        for hour in [0, 12]:
            dt = now - timedelta(days=days_ago)
            dt = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
            df, query_time = try_fetch_igra2(station, dt.year, dt.month, dt.day, dt.hour)
            if df is not None and not df.empty:
                print(f"🎯 最终使用: {query_time.strftime('%Y-%m-%d %HZ')}")
                return df, query_time
        # 每尝试一天打印一个点，表示进度
        print(f"  第 {days_ago + 1} 天无数据，继续往前...")

    print("❌ 所有尝试均失败")
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

    # 🔥 IGRA2 列名映射
    # 常见列名: pressure, temperature, dewpoint, u_wind, v_wind
    # 如果列名不同，需要适配
    try:
        # 尝试标准列名
        if 'pressure' in df.columns:
            p = df['pressure'].values * units.hPa
        elif 'PRES' in df.columns:
            p = df['PRES'].values * units.hPa
        else:
            raise KeyError("找不到气压列")

        if 'temperature' in df.columns:
            T = df['temperature'].values * units.degC
        elif 'TEMP' in df.columns:
            T = df['TEMP'].values * units.degC
        else:
            raise KeyError("找不到温度列")

        if 'dewpoint' in df.columns:
            Td = df['dewpoint'].values * units.degC
        elif 'DEWP' in df.columns:
            Td = df['DEWP'].values * units.degC
        else:
            # 如果没有露点，尝试从比湿计算
            print("⚠️ 无露点列，尝试从相对湿度计算...")
            if 'RH' in df.columns:
                rh = df['RH'].values * units.percent
                Td = mpcalc.dewpoint_from_relative_humidity(T, rh)
            else:
                Td = T - 5 * units.degC  # 粗略估计
                print("⚠️ 使用粗略估计的露点温度")

        if 'u_wind' in df.columns:
            u = df['u_wind'].values * units.knot
        elif 'UWND' in df.columns:
            u = df['UWND'].values * units.knot
        else:
            u = np.zeros(len(p)) * units.knot

        if 'v_wind' in df.columns:
            v = df['v_wind'].values * units.knot
        elif 'VWND' in df.columns:
            v = df['VWND'].values * units.knot
        else:
            v = np.zeros(len(p)) * units.knot

    except Exception as e:
        print(f"❌ 数据提取失败: {e}")
        print(f"可用列: {df.columns.tolist()}")
        raise

    # 过滤无效数据
    valid_mask = (p.magnitude > 0) & (T.magnitude > -100) & (T.magnitude < 60) & (p.magnitude < 1100)
    if not all(valid_mask):
        p = p[valid_mask]; T = T[valid_mask]; Td = Td[valid_mask]
        u = u[valid_mask]; v = v[valid_mask]

    if len(p) < 5:
        raise ValueError(f"有效数据点太少 ({len(p)})")

    # 去重
    temp_df = pd.DataFrame({
        'pressure': p.magnitude,
        'temperature': T.magnitude,
        'dewpoint': Td.magnitude,
        'u_wind': u.magnitude,
        'v_wind': v.magnitude
    })
    temp_df = temp_df.drop_duplicates(subset=['pressure'])
    p = temp_df['pressure'].values * units.hPa
    T = temp_df['temperature'].values * units.degC
    Td = temp_df['dewpoint'].values * units.degC
    u = temp_df['u_wind'].values * units.knot
    v = temp_df['v_wind'].values * units.knot

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
    if query_time:
        title += f'数据源: IGRA2\n'
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

    # 使用 IGRA2 站点 ID
    df, query_time = get_latest_sounding(IGRA_STATION)
    generate_plot(df, STATION, OUTPUT_FILE, query_time)
    print("=" * 60)
    print("🎉 完成！")


if __name__ == '__main__':
    main()