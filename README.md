# 站点45004 (香港) 探空图

自动生成并更新香港站点的气象探空图 (T-logP 图)。

## 🌐 在线访问

[https://your-username.github.io/sounding_45004](https://your-username.github.io/sounding_45004)

## 📋 说明

- **站点**: 45004 (香港国际机场)
- **数据来源**: 怀俄明大学探空数据库
- **更新频率**: 每日 00Z 和 12Z (UTC)
- **自动更新**: 通过 GitHub Actions 自动运行

## 🛠️ 技术栈

- Python 3.11
- MetPy (气象计算与绘图)
- Siphon (数据获取)
- Matplotlib (绘图)
- GitHub Actions (自动化)

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `index.html` | 主页面 |
| `generate_sounding.py` | 数据获取和绘图脚本 |
| `requirements.txt` | Python 依赖 |
| `.github/workflows/update_sounding.yml` | 自动更新工作流 |

## 🚀 本地运行

```bash
pip install -r requirements.txt
python generate_sounding.py