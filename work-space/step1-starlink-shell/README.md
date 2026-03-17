# Starlink Shell 工具集（TLE 壳层划分/阈值扫描/统计汇总）

本目录包含 2 个脚本，用于从 TLE（Two-Line Element Set）中提取轨道参数（主要是**高度**与**倾角**），并据此把卫星划分为“壳层（shell）”，以及对壳层结果做阈值扫描与统计汇总。

- `divide_constellation_shells.py`：读取 TLE，计算高度/倾角，按阈值把卫星划分到壳层；支持按 shell 输出 `.tle` 文件，并可额外输出每个 shell 的统计汇总（CSV/JSON）。
- `sweep_shell_clustering.py`：对一组 (高度阈值, 倾角阈值) 组合做扫描，输出每组阈值下最大簇（cluster）的 top-k 大小，便于选阈值。

## 依赖

- Python 3
- `numpy`（仅 `divide_constellation_shells.py` 需要）

建议在本目录运行，或确保 Python 能找到同目录下的模块（因为 `sweep_shell_clustering.py` 会 `import divide_constellation_shells`）。

## 输入：TLE 文件格式

`divide_constellation_shells.py` 和 `sweep_shell_clustering.py` 期望的 TLE 文件是 **3 行一组** 的“无额外头部”格式：

1. 第 1 行：卫星名称（任意文本）
2. 第 2 行：TLE line 1（以 `1` 开头的那行）
3. 第 3 行：TLE line 2（以 `2` 开头的那行）

脚本会从 TLE line 2 中解析：
- 倾角（inclination，单位：deg）
- 平均运动（mean motion，单位：rev/day）
- 偏心率（eccentricity）

并由平均运动按开普勒第三定律近似计算半长轴与平均高度（高度 = 半长轴 - 地球平均半径 6371 km）。

## 1) 壳层划分：divide_constellation_shells.py

### 基本用法

```bash
python divide_constellation_shells.py tles.txt
```

### 指定阈值

- `--altitude-tolerance`：高度阈值（km）
- `--inclination-tolerance`：倾角阈值（deg）

```bash
python divide_constellation_shells.py tles.txt --altitude-tolerance 50 --inclination-tolerance 1.0
```

### 划分方法

- `--method clustering`（默认）：**连通分量聚类（传递闭包）**。若两颗卫星满足

  $|\Delta alt|\le alt\_tol$ 且 $|\Delta inc|\le inc\_tol$

  则认为两者相邻；shell 是该相邻关系下的连通分量（会做传递闭包）。实现上使用“网格索引 + 并查集（union-find）”加速。

- `--method grid`：简单网格分箱：

  `alt_bin = int(altitude / alt_tol)`

  `inc_bin = int(inclination / inc_tol)`

  同一个 bin 里的卫星归为同一 shell。

示例：

```bash
python divide_constellation_shells.py tles.txt --method grid --altitude-tolerance 10 --inclination-tolerance 0.1
```

### 导出结果

```bash
python divide_constellation_shells.py tles.txt \
  --altitude-tolerance 10 \
  --inclination-tolerance 0.1 \
  --output-tle-dir shells_tle \
  --output-tle-prefix shell \
  --output-shell-stats-csv out/shell_stats.csv \
  --output-shell-stats-json out/shell_stats.json
```

- `--output-tle-dir`：把每个 shell 写成一个独立的 `.tle` 文件（每颗卫星 3 行：name、tle1、tle2）。文件名形如 `shell_<shell_id>.tle`（前缀可用 `--output-tle-prefix` 修改）。
- `--output-shell-stats-csv` / `--output-shell-stats-json`：输出每个 shell 的统计汇总（count、alt/inc 的 min/max/mean/std/median，若存在则包含 ecc 与 mean-motion 的统计）。

### 输出到终端的摘要

脚本会打印：
- shell 数量、总卫星数
- 每个 shell 的卫星数、高度范围、倾角范围（默认按 shell 内卫星数降序展示）
- 整体星座的高度/倾角统计（min/max/mean/std）

## 2) 阈值扫描：sweep_shell_clustering.py

这个脚本用于“选阈值”：给定多个高度阈值与倾角阈值组合，计算每组阈值下最大的几个簇的大小。

它采用与 `divide_constellation_shells.py --method clustering` 相同的**连通分量聚类（transitive closure）**定义：
- 若 A 与 B 在矩形邻域内则连边
- 聚类结果为图的连通分量

为了效率，脚本使用“网格索引 + 并查集（union-find）”仅比较相邻 3x3 cell 内的点。

### 示例

```bash
python sweep_shell_clustering.py tles.txt \
  --alt 1 5 10 20 \
  --inc 0.01 0.05 0.1 0.5 \
  --top-k 5
```

输出为 TSV 风格：

- `alt_tol_km`
- `inc_tol_deg`
- `top_sizes`（一个列表，例如 `[1800, 1700, 200]`）
