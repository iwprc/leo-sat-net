# 轨道面统计（从 TLE 估计 orbit planes）

本目录用于从 TLE 文件中提取 **RAAN（升交点赤经）** 与 **inclination（倾角）**，并按 RAAN 聚类来估计：

- 轨道面数量（orbit planes / orbit count）
- 每个轨道面的卫星数量

核心脚本：
- `count_orbits_from_tle.py`

本目录下常见的输入文件形如 `shell_*.tle`（通常来自上一步按高度/倾角分 shell 后导出的 TLE 文件）。

## 依赖

- Python 3（仅标准库，无第三方依赖）

## 输入：TLE 支持的两种格式

脚本会自动识别以下两种 TLE 排布：

1) **两行一组（无名称行）**

```
1 .....
2 .....
1 .....
2 .....
...
```

2) **三行一组（第一行是名称）**

```
SAT NAME
1 .....
2 .....
SAT NAME
1 .....
2 .....
...
```

解析内容：
- 从 line 1 提取 `satnum`（NORAD catalog number）：`l1[2:7]`
- 从 line 2 提取：
  - 倾角 `inclination_deg`：`parts[2]`
  - RAAN `raan_deg`：`parts[3]`（对 360 取模）

## 方法说明：RAAN 一维聚类（含 0/360° 环绕）

给定阈值 `--raan-threshold`（默认 2.0°），脚本把所有卫星的 RAAN 按数值排序后，按“相邻差值不超过阈值”进行分段聚类：

- 若当前 RAAN 与同簇最后一个 RAAN 的差值 `<= threshold`，则归入同簇
- 否则开启新簇
- 最后额外处理 **环绕合并**：如果最小 RAAN 与最大 RAAN 之间跨 360° 的距离也 `<= threshold`，则把首尾两簇合并

每个簇代表一个“轨道面”。簇的代表 RAAN 通过圆形均值（circular mean）计算得到。

> 注意：这是一种启发式估计方法，结果对阈值较敏感。若你的 TLE 数据 RAAN 噪声更大或更小，建议调整 `--raan-threshold`。

## 用法

### 基本统计

```bash
python count_orbits_from_tle.py shell_371.tle
```

### 调整 RAAN 聚类阈值

```bash
python count_orbits_from_tle.py shell_371.tle --raan-threshold 1.0
python count_orbits_from_tle.py shell_371.tle --raan-threshold 3.0
```

### 只统计指定倾角范围（可选）

```bash
python count_orbits_from_tle.py shell_371.tle --min-inclination 50
python count_orbits_from_tle.py shell_371.tle --min-inclination 50 --max-inclination 60
```

### 导出 CSV

```bash
python count_orbits_from_tle.py shell_371.tle --output-csv shell_371_orbits.csv
```

CSV 字段：
- `orbit_index`：轨道面编号（从 1 开始；按平均 RAAN 从小到大排序）
- `satellite_count`：该轨道面的卫星数
- `mean_raan_deg`：该轨道面簇的圆形均值 RAAN（度）

## 典型输出

终端会打印：
- 卫星总数
- 轨道数（轨道面数）
- 每个轨道面的卫星数与平均 RAAN

如果提供 `--output-csv`，还会写入对应 CSV 并提示文件路径。
