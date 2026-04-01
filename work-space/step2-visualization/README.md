# 可视化（Cesium + TLE）

本目录包含一个把 TLE 星座生成 Cesium 可视化 HTML 的脚本，并内置“按 RAAN 聚类轨道面”的逻辑。

- 入口脚本：`viz.py`

同时还包含两个用于准备可视化输入数据的辅助脚本：

- `convert_ground_station_info.py`：把 `ground_station_info.csv` 转换为 `ground_stations.basic.txt` / `ground_stations.txt`
- `build_user_latlon_txt.py`：把 `user_distribution.csv` 补齐经纬度，生成可视化可读的用户点文件

生成的 HTML 会从 CDN 加载 Cesium 与 satellite.js（需要联网）。

## 依赖

- Python 3
- 运行时需要网络（Cesium / satellite.js 通过 jsdelivr/unpkg 加载）

辅助脚本的额外要求：
- `convert_ground_station_info.py`：仅标准库
- `build_user_latlon_txt.py`：仅标准库，但会访问 OpenStreetMap Nominatim（需要联网，且请求频率受限）

## 输入数据

### TLE 文件

`viz.py` 支持输入多个 TLE 文件（例如 `shell_371.tle shell_394.tle shell_674.tle`）。

TLE 支持 2 种排布：
- 2 行一组：`1 ...` + `2 ...`
- 3 行一组：`NAME` + `1 ...` + `2 ...`

脚本会把每颗卫星的 `tle_line1` / `tle_line2` 写入 HTML，并在浏览器端用 satellite.js 传播轨迹。

### 地面站 / 用户 / POP

目录中默认带了示例文件：
- `ground_stations.basic.txt`
- `user.txt`
- `pop.txt`

你也可以用参数替换路径：`--ground-stations`、`--users`、`--pops`。

## 轨道面聚类（与 count_orbits_from_tle.py 一致）

脚本会按 **shell 分组**，在每个 shell 内用 RAAN（升交点赤经）进行一维聚类来估计轨道面，并给每颗卫星写入 `orbit_id`。

聚类算法与 [work-space/step2-get-orbit/count_orbits_from_tle.py](../step2-get-orbit/count_orbits_from_tle.py) 保持一致：

- RAAN 排序
- 相邻差值 `<= --raan-threshold` 归为同一簇
- 处理 0/360° 环绕：若最小 RAAN 与最大 RAAN 跨 360° 的距离也 `<= threshold`，则合并首尾簇
- 按簇的圆形均值（circular mean）排序

`orbit_id` 采用 **1-based 编号**，`0` 保留给解析失败/unknown。

## 用法

### 生成 HTML（单个 TLE）

```bash
python viz.py shell_371.tle --output out.html
```

### 生成 HTML（多个 TLE，常用于多个 shell/星座一起看）

```bash
python viz.py shell_371.tle shell_394.tle shell_674.tle \
  --output satellites_visualization.html \
  --raan-threshold 2.0 \
  --duration-minutes 60 \
  --time-step-seconds 120
```

常用参数：
- `--raan-threshold`：按 RAAN 聚类轨道面的阈值（度），默认 2.0
- `--duration-minutes`：轨迹时长（分钟）
- `--time-step-seconds`：采样步长（秒），越小越平滑但更慢
- `--max-satellites`：限制可视化卫星数量
- `--max-users`：限制用户点数量

生成后用浏览器打开 HTML 文件即可。

## 辅助脚本

### 1) 地面站 CSV 转换：convert_ground_station_info.py

用途：
- 从 `ground_station_info.csv` 读取地面站（name/lon/lat），生成 Hypatia/本可视化脚本可读的地面站文本文件。

输入：
- `ground_station_info.csv`（位于本目录）

输出：
- `ground_stations.basic.txt`：每行 `id,name,lat,lon,ele`（ele 固定为 0.0）
- `ground_stations.txt`：在 basic 基础上追加 ECEF 坐标 `x,y,z`

运行：

```bash
python convert_ground_station_info.py
```

注意：
- 脚本会把地面站名称中的逗号替换为分号（因为后续某些解析器是用 `line.split(',')` 的方式读取）。

### 2) 用户分布补齐经纬度：build_user_latlon_txt.py

用途：
- 从 `user_distribution.csv`（城市,用户数）出发，为每个城市补齐经纬度。
- 优先使用地面站文件中已有的城市坐标（`ground_stations.basic.txt`），其次用内置的少量 `fixed_coordinates`，最后才调用 Nominatim 地理编码。

如果你已经有 `user.txt`（每行直接给出经纬度的用户点文件），则无需运行该脚本。

输入（默认写死在脚本里，位于本目录；该文件可能需要你自己提供）：
- `user_distribution.csv`
- `ground_stations.basic.txt`

输出（位于本目录）：
- `user_distribution_with_latlon.txt`：CSV，列为 `city,users,latitude,longitude`
- `user_distribution_with_latlon_unmatched.txt`：无法匹配/编码失败的城市名单
- `user_distribution_geocode_cache.csv`：地理编码缓存（避免重复请求）

运行：

```bash
python build_user_latlon_txt.py
```

重要注意事项：
- 该脚本会访问 `https://nominatim.openstreetmap.org/`，需要联网；并且内置 `time.sleep(1.0)` 控制请求频率。
- 脚本里 `base = Path('/home/yyr/hypatia/work-space/visualization')` 是绝对路径；如果换机器/换目录，需要改成你的实际路径，或改写为 `base = Path(__file__).resolve().parent`。
