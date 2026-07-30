#!/usr/bin/env python3
"""
站点45004探空图生成脚本
用于 GitHub Actions 自动运行
"""

import matplotlib
matplotlib.use('Agg')  # 无界面后端

import matplotlib.pyplot as plt
import metpy.calc as mpcalc
from metpy.plots import SkewT
from metpy.units import units
from siphon.simplewebservice.wyoming import WyomingUpperAir
from datetime import datetime, timedelta
import os
import sys
import traceback

STATION = '45004'
OUTPUT_DIR = 'images'
OUTPUT_FILE = f'{OUTPUT_DIR}/sounding_{STATION}.png'
STATION_NAME = '香港'

def get_latest_sounding(station):
    """获取最新的探空数据"""
    now = datetime.utcnow()
    # 确定最近的探空时间 (00Z 或 12Z)
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
        df = WyomingUpperAir.request_data(query_time, station)
        print(f"✅ 数据获取成功！共 {len(df)} 层")
        return df, query_time
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        # 尝试获取前一天的 12Z 数据作为备选
        print("⏳ 尝试获取前一天的 12Z 数据...")
        fallback_time = query_time - timedelta(days=1)
        fallback_time = fallback_time.replace(hour=12)
        try:
            df = WyomingUpperAir.request_data(fallback_time, station)
            print(f"✅ 备选数据获取成功！共 {len(df)} 层")
            return df, fallback_time
        except Exception as e2:
            print(f"❌ 备选数据也失败: {e2}")
            raise

def generate_plot(df, station, output_path, query_time):
    """生成探空图"""
    print("⏳ 正在生成探空图...")
    
    # 提取数据
    p = df['pressure'].values * units.hPa
    T = df['temperature'].values * units.degC
    Td = df['dewpoint'].values * units.degC
    u = df['u_wind'].values * units.knot
    v = df['v_wind'].values * units.knot
    
    # 去除无效数据
    valid_mask = (p > 0) & (T > -100) & (T < 60)
    if not all(valid_mask):
        print(f"⚠️ 发现 {sum(~valid_mask)} 个无效数据点，已过滤")
        p = p[valid_mask]
        T = T[valid_mask]
        Td = Td[valid_mask]
        u = u[valid_mask]
        v = v[valid_mask]
    
    # 计算物理量
    try:
        parcel_profile = mpcalc.parcel_profile(p, T[0], Td[0])
        cape, cin = mpcalc.cape_cin(p, T, Td, parcel_profile)
        k_index = mpcalc.k_index(p, T, Td)
        lcl_p, lcl_t = mpcalc.lcl(p[0], T[0], Td[0])
    except Exception as e:
        print(f"⚠️ 物理量计算部分失败: {e}")
        parcel_profile = p * 0 + 273  # 备用
        cape = cin = k_index = lcl_p = lcl_t = 0
    
    # 创建图形
    fig = plt.figure(figsize=(10, 12), dpi=120, facecolor='white')
    skew = SkewT(fig, rotation=35)
    
    # 绘制背景线
    skew.plot_dry_adiabats(linewidth=0.5, alpha=0.3, colors='#d4a574')
    skew.plot_moist_adiabats(linewidth=0.5, alpha=0.3, colors='#74a5d4')
    skew.plot_mixing_lines(linewidth=0.5, alpha=0.3, colors='#74d4a5')
    
    # 绘制数据
    skew.plot(p, T, 'r', linewidth=2.5, label='温度层结')
    skew.plot(p, Td, 'g', linewidth=2.5, label='露点层结')
    skew.plot(p, parcel_profile, 'k', linewidth=2, linestyle='--', 
              label='状态曲线 (气块)')
    
    # 标记 LCL
    if lcl_p and lcl_t and lcl_p > 0 and lcl_t > -100:
        skew.plot(lcl_p, lcl_t, 'ko', markersize=12, label='LCL')
        skew.plot(lcl_p, lcl_t, 'yo', markersize=6)
    
    # 绘制风羽 (仅保留部分层避免过密)
    step = max(1, len(p) // 20)
    skew.plot_barbs(p[::step], u[::step], v[::step], xloc=1.08, length=5)
    
    # 坐标轴
    skew.ax.set_ylim(1000, 100)
    skew.ax.set_xlim(-50, 50)
    skew.ax.set_ylabel('气压 (hPa)', fontsize=13, fontweight='bold')
    skew.ax.set_xlabel('温度 (°C)', fontsize=13, fontweight='bold')
    
    # 网格
    skew.ax.grid(True, linestyle='--', alpha=0.3)
    
    # 标题和参数信息
    cape_str = f'{cape:.1f}' if cape < 9999 else '>9999'
    title = f'站点 {station} ({STATION_NAME}) 探空图\n'
    title += f'时间: {query_time.strftime("%Y-%m-%d %H:00 UTC")}\n'
    title += f'CAPE: {cape_str} J/kg  |  K指数: {k_index:.1f} °C  |  LCL: {lcl_p:.0f} hPa'
    plt.title(title, fontsize=11, pad=15)
    plt.legend(loc='upper right', fontsize=9)
    
    # 保存
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    # 检查文件大小
    file_size = os.path.getsize(output_path) / 1024
    print(f"✅ 探空图已保存至: {output_path} ({file_size:.1f} KB)")

def main():
    print("=" * 60)
    print(f"📍 站点 {STATION} ({STATION_NAME}) 探空图生成器")
    print(f"🕐 运行时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    
    try:
        # 获取数据
        df, query_time = get_latest_sounding(STATION)
        
        # 生成图表
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