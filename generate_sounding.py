#!/usr/bin/env python3
"""
站点45004探空图生成脚本 - 修复所有 Quantity 比较问题
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
REGION = 'easia'  # 🔥 关键：东亚区域


def get_sounding_with_retry(station, query_time, max_retries=3):
    """带重试的数据获取"""
    for attempt in range(max_retries):
        try:
            print(f"  尝试 {attempt + 1}/{max_retries}...")
            df = WyomingUpperAir.request_data(query_time, station)
            return df
        except Exception as e:
            print(f"  ⚠️ 尝试 {attempt + 1} 失败: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"  等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                raise


def get_latest_sounding(station):
    """获取最新的探空数据"""
    now = datetime.utcnow()
    hour = now.hour

    if hour >= 13:
        target_hour = 12
    elif hour >= 1:
        target_hour = 0
    else:
        target_hour = 12

    query_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    if hour < 1 and target_hour == 12:
        query_time = query_time - timedelta(days=1)

    print(f"⏳ 正在获取 {query_time.strftime('%Y-%m-%d %H:00Z')} 的探空数据...")
    print(f"📍 站点: {station} ({STATION_NAME})")

    try:
        df = get_sounding_with_retry(station, query_time)
        print(f"✅ 数据获取成功！共 {len(df)} 层")
        return df, query_time
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        print("⏳ 尝试获取前一天的 12Z 数据...")
        fallback_time = query_time - timedelta(days=1)
        fallback_time = fallback_time.replace(hour=12)
        try:
            df = get_sounding_with_retry(station, fallback_time)
            print(f"✅ 备选数据获取成功！共 {len(df)} 层")
            return df, fallback_time
        except Exception as e2:
            print(f"❌ 备选数据也失败: {e2}")
            raise


def generate_plot(df, station, output_path, query_time):
    """生成探空图"""
    print("⏳ 正在生成探空图...")

    if df.empty:
        raise ValueError("数据为空，无法生成探空图")

    # 提取数据（带单位）
    try:
        p = df['pressure'].values * units.hPa
        T = df['temperature'].values * units.degC
        Td = df['dewpoint'].values * units.degC
        u = df['u_wind'].values * units.knot
        v = df['v_wind'].values * units.knot
    except KeyError as e:
        print(f"❌ 数据列缺失: {e}")
        print(f"可用列: {df.columns.tolist()}")
        raise

    # 过滤无效数据
    valid_mask = (p.magnitude > 0) & (T.magnitude > -100) & (T.magnitude < 60) & (p.magnitude < 1100)

    if not all(valid_mask):
        print(f"⚠️ 发现 {sum(~valid_mask)} 个无效数据点，已过滤")
        p = p[valid_mask]
        T = T[valid_mask]
        Td = Td[valid_mask]
        u = u[valid_mask]
        v = v[valid_mask]

    if len(p) < 5:
        raise ValueError(f"有效数据点太少 ({len(p)} 层)，无法生成探空图")

    # 去除重复气压层
    df_filtered = df[valid_mask]
    df_unique = df_filtered.drop_duplicates(subset=['pressure'])
    if len(df_unique) < len(df_filtered):
        print(f"⚠️ 去除了 {len(df_filtered) - len(df_unique)} 个重复气压层")
        p = df_unique['pressure'].values * units.hPa
        T = df_unique['temperature'].values * units.degC
        Td = df_unique['dewpoint'].values * units.degC
        u = df_unique['u_wind'].values * units.knot
        v = df_unique['v_wind'].values * units.knot

    # 计算物理量
    try:
        parcel_profile = mpcalc.parcel_profile(p, T[0], Td[0])
        cape, cin = mpcalc.cape_cin(p, T, Td, parcel_profile)
        k_index = mpcalc.k_index(p, T, Td)
        lcl_p, lcl_t = mpcalc.lcl(p[0], T[0], Td[0])
    except Exception as e:
        print(f"⚠️ 物理量计算部分失败: {e}")
        try:
            parcel_profile = mpcalc.parcel_profile(p, T[0], Td[0])
            cape = cin = 0 * units('J/kg')
            k_index = 0 * units('degC')
            lcl_p, lcl_t = p[0], T[0]
        except:
            parcel_profile = p * 0 + 273
            cape = cin = 0 * units('J/kg')
            k_index = 0 * units('degC')
            lcl_p, lcl_t = None, None

    # 创建图形
    fig = plt.figure(figsize=(10, 12), dpi=120, facecolor='white')
    skew = SkewT(fig, rotation=35)

    # 背景线
    skew.plot_dry_adiabats(linewidth=0.5, alpha=0.3, colors='#d4a574')
    skew.plot_moist_adiabats(linewidth=0.5, alpha=0.3, colors='#74a5d4')
    skew.plot_mixing_lines(linewidth=0.5, alpha=0.3, colors='#74d4a5')

    # 数据
    skew.plot(p, T, 'r', linewidth=2.5, label='温度层结')
    skew.plot(p, Td, 'g', linewidth=2.5, label='露点层结')
    skew.plot(p, parcel_profile, 'k', linewidth=2, linestyle='--',
              label='状态曲线 (气块)')

    # 安全地检查 LCL
    lcl_valid = False
    if lcl_p is not None and lcl_t is not None:
        try:
            if (hasattr(lcl_p, 'magnitude') and hasattr(lcl_t, 'magnitude') and
                not np.isnan(lcl_p.magnitude) and not np.isnan(lcl_t.magnitude) and
                lcl_p.magnitude > 0 and lcl_t.magnitude > -100 and lcl_p.magnitude < 1100):
                lcl_valid = True
        except Exception:
            lcl_valid = False

    if lcl_valid:
        skew.plot(lcl_p, lcl_t, 'ko', markersize=12, label='LCL')
        skew.plot(lcl_p, lcl_t, 'yo', markersize=6)

    # 风羽
    step = max(1, len(p) // 15)
    if step > 0:
        skew.plot_barbs(p[::step], u[::step], v[::step], xloc=1.08, length=5)

    # 坐标轴
    skew.ax.set_ylim(1000, 100)
    skew.ax.set_xlim(-50, 50)
    skew.ax.set_ylabel('气压 (hPa)', fontsize=13, fontweight='bold')
    skew.ax.set_xlabel('温度 (°C)', fontsize=13, fontweight='bold')
    skew.ax.grid(True, linestyle='--', alpha=0.3)

    # ========== 🔥 修复标题中的 Quantity 比较 ==========
    # 提取 cape 数值
    try:
        if cape is not None and hasattr(cape, 'magnitude'):
            cape_val = cape.magnitude
        else:
            cape_val = 0
        if np.isnan(cape_val):
            cape_val = 0
    except:
        cape_val = 0
    cape_str = f'{cape_val:.1f}' if cape_val < 9999 else '>9999'

    # 提取 k_index 数值
    try:
        if k_index is not None and hasattr(k_index, 'magnitude'):
            k_index_val = k_index.magnitude
        else:
            k_index_val = 0
        if np.isnan(k_index_val):
            k_index_val = 0
    except:
        k_index_val = 0

    # LCL 字符串
    lcl_str = f'{lcl_p.magnitude:.0f}' if lcl_valid else 'N/A'

    # 构建标题
    title = f'站点 {station} ({STATION_NAME}) 探空图\n'
    title += f'时间: {query_time.strftime("%Y-%m-%d %H:00 UTC")}\n'
    title += f'CAPE: {cape_str} J/kg  |  K指数: {k_index_val:.1f} °C  |  LCL: {lcl_str} hPa'
    plt.title(title, fontsize=11, pad=15)
    plt.legend(loc='upper right', fontsize=9)

    # 保存
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path) / 1024
        print(f"✅ 探空图已保存至: {output_path} ({file_size:.1f} KB)")
        if file_size < 10:
            print(f"⚠️ 文件大小异常 ({file_size:.1f} KB)，可能生成不完整")
    else:
        raise RuntimeError(f"文件保存失败: {output_path}")


def main():
    print("=" * 60)
    print(f"📍 站点 {STATION} ({STATION_NAME}) 探空图生成器")
    print(f"🕐 运行时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    try:
        df, query_time = get_latest_sounding(STATION)
        generate_plot(df, STATION, OUTPUT_FILE, query_time)
        print("=" * 60)
        print("🎉 完成！")
    except Exception as e:
        print("=" * 60)
        print(f"❌ 错误: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()