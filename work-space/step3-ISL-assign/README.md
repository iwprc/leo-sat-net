# Step 3: ISL 构建与可视化

本目录包含两个脚本：

- `makeisl.py`：根据 TLE 为低轨卫星构建激光星间链路（ISL），输出 `isls.txt`
- `vizisl.py`：读取 `isls.txt`，提取前十大 ISL 连通块并生成 Cesium 可视化 HTML，同时分别输出“纯统计 JSON”和“可视化数据 JSON”

两者默认都以本目录中的 `starlink-TLE-20260403.txt` 为输入。

## 输入与输出

### 输入

- `starlink-TLE-20260403.txt`
    - 采用 3 行一组格式：`name` + `TLE line 1` + `TLE line 2`
    - 脚本也兼容首行存在 `n_orbits n_sats_per_orbit` 头部的情况，并会自动跳过该头部

### 输出

- `isls.txt`
    - 与 `/home/yyr/hypatia/satgenpy/README.md` 中的 `isls.txt` 格式一致
    - 每行一条无向边：`a b`
    - 满足 `0 <= a < b < num_satellites`

- `vizisl_top10.html`
    - 用 Cesium 展示前十大 ISL 连通块中的卫星及其星间链路

- `vizisl_top10_stats.json`
    - 轻量统计文件，只保存图级统计和前十大连通块摘要

- `vizisl_top10_data.json`
    - 详细数据文件，保存前十大连通块的卫星、TLE 和 ISL 边信息

## makeisl.py 的实现逻辑

脚本的实现与原始设计一致，但做了几处工程化约束：

- 轨道参数直接从 TLE line 2 解析，包括半长轴、倾角、升交点赤经
- 位置预测使用 `sgp4`
- 平均距离定义为：从 `2026-04-03 00:00:00 UTC` 开始，向后 100 分钟，每 1 分钟采样一次，对两星间直线距离取平均
- 为避免在 1 万颗卫星规模上做全对全搜索，脚本按 `半长轴 / 倾角 / RAAN` 建立离散索引，只在邻近桶内搜索候选卫星

### 轨道内链路

脚本为每颗卫星维护两个轨道内终端状态：

- `forward terminal`
- `backward terminal`

遍历每颗卫星 `x`。若 `x` 的前向终端尚未占用，则寻找可向前连接的卫星 `y`。候选必须满足：

1. `|a_x - a_y| < 1 km`
2. `|inc_x - inc_y| < 1°`
3. `|RAAN_x - RAAN_y| < 2°`，这里使用最短圆周差值
4. `y` 相对 `x` 的纬度幅角在 `[1°, 31°]` 内
5. `y` 的后向终端尚未占用

若候选集合非空，则选择平均距离最小的 `y` 建边，并标记：

- `x.forward = used`
- `y.backward = used`

### 轨道间链路

脚本先把“已建立轨道内链路的卫星”按联通块分组，并将这些联通块视为轨道。随后：

- 每个轨道内按纬度幅角升序遍历卫星
- 维护 `tag` 变量
    - `tag = 0`：向左找邻轨卫星
    - `tag = 1`：向右找邻轨卫星
- 仅当本次成功建边时才执行 `tag ^= 1`

每颗卫星有一个轨道间侧向终端 `side terminal`。若卫星 `x` 的侧向终端未占用，则尝试寻找候选 `y`：

1. `|a_x - a_y| < 1 km`
2. `|inc_x - inc_y| < 1°`
3. `tag = 1` 时，`RAAN_y - RAAN_x` 的最短有向差值在 `[1°, 31°]`
4. `tag = 0` 时，`RAAN_y - RAAN_x` 的最短有向差值在 `[-31°, -1°]`
5. `x` 与 `y` 在起始采样时刻形成的地心角 `< 31°`
6. `y` 的侧向终端未占用

若候选集合非空，则选择平均距离最小的 `y` 建边，并标记双方侧向终端为占用。

## makeisl.py 用法

### 使用默认输入输出

```bash
python makeisl.py
```

这会读取：

- `./starlink-TLE-20260403.txt`

并生成：

- `./isls.txt`

### 指定输入输出

```bash
python makeisl.py \
    --input starlink-TLE-20260403.txt \
    --output isls.txt
```

### 调整采样窗口

```bash
python makeisl.py \
    --start-time 2026-04-03T00:00:00Z \
    --duration-minutes 100 \
    --sample-interval-minutes 1
```

参数说明：

- `--start-time`：采样起点，默认 `2026-04-03T00:00:00Z`
- `--duration-minutes`：采样总时长，默认 `100`
- `--sample-interval-minutes`：采样间隔，默认 `1`

### 终端输出统计

运行后会在终端打印：

- 卫星总数
- 轨道内 ISL 数量
- 识别出的轨道联通块数量
- 轨道间 ISL 数量
- 总 ISL 数量
- 输出文件路径

在当前提供的 `starlink-TLE-20260403.txt` 上，脚本一次实跑得到：

- `satellites=10119`
- `intra_orbit_isls=7207`
- `orbits=1280`
- `inter_orbit_isls=4132`
- `total_isls=11339`

## vizisl.py 的功能

`vizisl.py` 针对 `makeisl.py` 生成的 `isls.txt` 做后处理。

它会：

1. 读取全部卫星与 ISL 图
2. 计算所有 ISL 连通块
3. 按连通块内卫星数降序排序
4. 取前 `K` 个连通块，默认 `K = 10`
5. 生成一个 Cesium HTML 页面，展示这些连通块中的卫星和链路
6. 输出轻量统计 JSON 文件
7. 输出可视化数据 JSON 文件

相比 step2 中“全量轨迹动画”的逻辑，这里做了一个更适合 step3 的改进：

- 只展示前十大连通块
- 采用单时刻快照，而不是整段轨迹动画
- 重点放在“连通结构”和“图统计”上，而不是全星座轨迹回放

浏览器页面中包含：

- 前十大连通块的独立颜色
- 每个连通块的显示/隐藏开关
- 每个连通块内北上卫星 / 南下卫星的独立显示开关
- 定位到单个连通块的按钮
- 全局统计信息
- 每个连通块的节点数、边数、平均度、密度、平均半长轴、平均倾角

当前可视化还做了两点显示约束：

- 被地球遮挡的卫星不再通过关闭深度测试的方式强制显示
- 当某个连通块只显示北上或南下卫星时，仅保留对应可见端点之间的 ISL 线段

## vizisl.py 用法

### 基本用法

```bash
python vizisl.py
```

默认读取：

- `./starlink-TLE-20260403.txt`
- `./isls.txt`

默认生成：

- `./vizisl_top10.html`
- `./vizisl_top10_stats.json`
- `./vizisl_top10_data.json`

### 指定文件路径

```bash
python vizisl.py \
    --input-tle starlink-TLE-20260403.txt \
    --input-isls isls.txt \
    --html-output vizisl_top10.html \
    --stats-output vizisl_top10_stats.json \
    --data-output vizisl_top10_data.json
```

### 调整连通块数量与快照时间

```bash
python vizisl.py \
    --top-k 10 \
    --start-time 2026-04-03T00:00:00Z
```

参数说明：

- `--top-k`：可视化前多少个连通块，默认 `10`
- `--start-time`：浏览器中用于 TLE 快照传播的时刻，默认 `2026-04-03T00:00:00Z`
- `--data-output`：详细可视化数据文件路径，默认 `vizisl_top10_data.json`

## vizisl_top10_stats.json 的内容

JSON 文件会包含：

- 全图卫星总数
- 全图 ISL 总数
- 连通块总数
- 非平凡连通块数
- 孤立卫星数量
- 前十大连通块的统计信息

每个连通块的统计字段包括：

- `satellite_count`
- `edge_count`
- `average_degree`
- `density`
- `min_satellite_id`
- `max_satellite_id`
- `mean_semi_major_axis_km`
- `mean_inclination_deg`
- `mean_raan_deg`

这个文件不再包含逐卫星 TLE 与边列表，因此更适合直接查看、版本管理和后续统计分析。

## vizisl_top10_data.json 的内容

该文件保存前十大连通块的详细可视化数据，包括：

- 每个连通块的摘要统计
- 每个连通块内所有卫星的 `sid`、名称、`tle1`、`tle2`
- 每个连通块内所有 ISL 边

这个文件体积会明显大于 `vizisl_top10_stats.json`，主要供前端可视化或进一步图分析使用。

## 依赖

Python 侧依赖：

- `numpy`
- `sgp4`

浏览器侧依赖：

- `Cesium`
- `satellite.js`

这两个前端库由生成的 HTML 在运行时通过 CDN 加载，因此浏览器打开页面时需要联网。

## 推荐流程

```bash
python makeisl.py
python vizisl.py
```

执行后：

- `isls.txt` 用于后续 Hypatia / satgenpy 流程
- `vizisl_top10.html` 用于人工检查连通结构
- `vizisl_top10_stats.json` 用于统计分析或后续处理
- `vizisl_top10_data.json` 用于可视化数据复用或进一步图分析

