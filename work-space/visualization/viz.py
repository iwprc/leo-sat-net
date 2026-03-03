#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能：读取 TLE 文件，生成 Cesium 卫星轨道可视化 HTML。
输入：TLE 文件（支持 3 行格式：名称 + line1 + line2，也支持 2 行格式：line1 + line2）
输出：默认 satellites_visualization.html
"""

import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


CITY_NAME_ZH_MAP = {
    "beijing": "北京",
    "tianjin": "天津",
    "shijiazhuang": "石家庄",
    "taiyuan": "太原",
    "hohhot": "呼和浩特",
    "shenyang": "沈阳",
    "changchun": "长春",
    "harbin": "哈尔滨",
    "shanghai": "上海",
    "nanjing": "南京",
    "hangzhou": "杭州",
    "hefei": "合肥",
    "fuzhou": "福州",
    "nanchang": "南昌",
    "jinan": "济南",
    "zhengzhou": "郑州",
    "wuhan": "武汉",
    "changsha": "长沙",
    "guangzhou": "广州",
    "nanning": "南宁",
    "haikou": "海口",
    "chongqing": "重庆",
    "chengdu": "成都",
    "guiyang": "贵阳",
    "kunming": "昆明",
    "lhasa": "拉萨",
    "xi'an": "西安",
    "xian": "西安",
    "lanzhou": "兰州",
    "xining": "西宁",
    "yinchuan": "银川",
    "urumqi": "乌鲁木齐",
    "hong kong": "香港",
    "macau": "澳门",
    "macao": "澳门",
    "taipei": "台北",
}


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cesium TLE Satellite Visualization</title>
    <script src="https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/Cesium.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/Widgets/widgets.css">
    <script src="https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js"></script>
    <style>
        html, body, #cesiumContainer {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
            background-color: black;
        }
        #infoPanel {
            position: absolute;
            top: 10px;
            left: 10px;
            background-color: rgba(0, 0, 0, 0.72);
            color: white;
            padding: 10px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 12px;
            z-index: 1000;
            max-width: 340px;
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div id="cesiumContainer"></div>
    <div id="infoPanel">
        <div>卫星数量：__SAT_COUNT__</div>
        <div>地面站数量：__GS_COUNT__</div>
        <div>轨迹时长：__DURATION_MINUTES__ 分钟</div>
        <div>采样步长：__TIME_STEP_SECONDS__ 秒</div>
        <div>TLE 起始时刻：<span id="tleEpochTime">__TLE_START_TIME_LABEL__</span></div>
        <div>北上数量：<span id="northboundCount">0</span></div>
        <div>南下数量：<span id="southboundCount">0</span></div>
        <div>方向未知：<span id="unknownDirectionCount">0</span></div>
        <div style="margin-top: 6px;">
            <label style="display: block;"><input type="checkbox" id="filterNorthOnly"> 只显示北上</label>
            <label style="display: block;"><input type="checkbox" id="filterSouthOnly"> 只显示南下</label>
        </div>
        <div>图例：北上=实线+青色描边；南下=虚线+洋红描边</div>
        <div>状态：<span id="status">初始化中...</span></div>
        <div>时间：<span id="currentTime"></span></div>
        <div>点击卫星查看详情</div>
    </div>

    <script>
        const statusEl = document.getElementById('status');
        if (typeof Cesium === 'undefined') {
            statusEl.textContent = 'Cesium 加载失败（网络或 CDN 不可达）';
            throw new Error('Cesium is not loaded');
        }
        if (typeof satellite === 'undefined') {
            statusEl.textContent = 'satellite.js 加载失败（网络或 CDN 不可达）';
            throw new Error('satellite.js is not loaded');
        }

        Cesium.buildModuleUrl.setBaseUrl('https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/');

        const viewer = new Cesium.Viewer('cesiumContainer', {
            timeline: true,
            animation: true,
            baseLayerPicker: false,
            geocoder: false,
            homeButton: true,
            sceneModePicker: true,
            navigationHelpButton: false,
            fullscreenButton: true,
            sceneMode: Cesium.SceneMode.SCENE2D,
            imageryProvider: new Cesium.UrlTemplateImageryProvider({
                url: 'https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/Assets/Textures/NaturalEarthII/{z}/{x}/{reverseY}.jpg',
                maximumLevel: 2,
                credit: 'Natural Earth II via Cesium'
            }),
            terrainProvider: new Cesium.EllipsoidTerrainProvider()
        });

        viewer.scene.globe.show = true;
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#223344');
        viewer.scene.globe.enableLighting = false;
        viewer.scene.globe.depthTestAgainstTerrain = false;
        viewer.scene.skyAtmosphere.show = false;
        viewer.scene.skyBox.show = false;
        viewer.scene.fog.enabled = false;
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0a0f1f');
        viewer.scene.screenSpaceCameraController.enableTranslate = true;
        viewer.scene.screenSpaceCameraController.enableZoom = true;
        viewer.scene.screenSpaceCameraController.enableRotate = false;
        viewer.scene.screenSpaceCameraController.enableTilt = false;
        viewer.scene.screenSpaceCameraController.enableLook = false;
        viewer.scene.screenSpaceCameraController.inertiaTranslate = 0.85;
        viewer.scene.screenSpaceCameraController.inertiaZoom = 0.8;
        viewer._cesiumWidget._creditContainer.style.display = 'none';
        statusEl.textContent = '正在计算轨道...（底图: NaturalEarthII）';

        const rawSatellites = __SATELLITES_JSON__;
        const rawGroundStations = __GROUND_STATIONS_JSON__;
        const durationMinutes = __DURATION_MINUTES__;
        const timeStepInSeconds = __TIME_STEP_SECONDS__;
        const tleStartTime = Cesium.JulianDate.fromIso8601('__TLE_START_TIME_ISO__');
        const filterNorthOnlyEl = document.getElementById('filterNorthOnly');
        const filterSouthOnlyEl = document.getElementById('filterSouthOnly');

        const colors = [
            Cesium.Color.RED,
            Cesium.Color.GREEN,
            Cesium.Color.BLUE,
            Cesium.Color.YELLOW,
            Cesium.Color.PURPLE,
            Cesium.Color.CYAN,
            Cesium.Color.ORANGE,
            Cesium.Color.LIME,
            Cesium.Color.AQUA,
            Cesium.Color.WHITE
        ];

        const startTime = tleStartTime;
        const stopTime = Cesium.JulianDate.addSeconds(startTime, durationMinutes * 60, new Cesium.JulianDate());

        const satelliteEntities = [];
        const groundStationEntities = [];
        let failedCount = 0;

        const showLabels = rawSatellites.length <= 200;
        const showPaths = rawSatellites.length <= 600;

        rawSatellites.forEach((sat, index) => {
            try {
                const satrec = satellite.twoline2satrec(sat.tle_line1, sat.tle_line2);
                const positionProperty = new Cesium.SampledPositionProperty();

                let currentTime = Cesium.JulianDate.clone(startTime);
                let sampleCount = 0;
                while (Cesium.JulianDate.compare(currentTime, stopTime) <= 0) {
                    const jsDate = Cesium.JulianDate.toDate(currentTime);
                    const pv = satellite.propagate(satrec, jsDate);
                    if (pv.position) {
                        const gmst = satellite.gstime(jsDate);
                        const ecf = satellite.eciToEcf(pv.position, gmst);
                        const samplePosition = new Cesium.Cartesian3(ecf.x * 1000, ecf.y * 1000, ecf.z * 1000);
                        positionProperty.addSample(
                            currentTime,
                            samplePosition
                        );
                        sampleCount += 1;
                    }
                    currentTime = Cesium.JulianDate.addSeconds(currentTime, timeStepInSeconds, new Cesium.JulianDate());
                }

                if (sampleCount === 0) {
                    failedCount += 1;
                    return;
                }

                const color = colors[sat.orbit_id % colors.length];
                const entity = viewer.entities.add({
                    name: sat.name,
                    position: positionProperty,
                    orientation: new Cesium.VelocityOrientationProperty(positionProperty),
                    point: {
                        pixelSize: 10,
                        color: color,
                        outlineColor: Cesium.Color.WHITE,
                        outlineWidth: 1.5
                    },
                    path: {
                        show: showPaths,
                        width: 1,
                        material: color.withAlpha(0.55),
                        leadTime: 0,
                        trailTime: durationMinutes * 60
                    },
                    label: {
                        text: sat.name,
                        font: '12px sans-serif',
                        show: showLabels,
                        showBackground: true,
                        backgroundColor: new Cesium.Color(0.1, 0.1, 0.1, 0.7),
                        pixelOffset: new Cesium.Cartesian2(0, -16),
                        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 3000000)
                    },
                    description: `卫星名称: ${sat.name}<br/>方向: unknown<br/>TLE Line 1: ${sat.tle_line1}<br/>TLE Line 2: ${sat.tle_line2}`
                });

                entity.baseName = sat.name;
                entity.baseColor = color;
                entity.directionKey = 'unknown';
                entity.tleLine1 = sat.tle_line1;
                entity.tleLine2 = sat.tle_line2;

                satelliteEntities.push(entity);
            } catch (error) {
                failedCount += 1;
                console.error(`解析卫星 ${sat.name} 失败:`, error);
            }
        });

        const showGroundLabels = rawGroundStations.length <= 200;
        rawGroundStations.forEach((gs) => {
            const position = Cesium.Cartesian3.fromDegrees(gs.longitude_deg, gs.latitude_deg, gs.elevation_m);
            const displayName = gs.name_zh || gs.name;
            const entity = viewer.entities.add({
                name: `GS-${gs.id}-${displayName}`,
                position,
                point: {
                    pixelSize: 8,
                    color: Cesium.Color.YELLOW,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 1.2,
                    disableDepthTestDistance: Number.POSITIVE_INFINITY
                },
                label: {
                    text: displayName,
                    font: '12px sans-serif',
                    show: showGroundLabels,
                    showBackground: true,
                    backgroundColor: new Cesium.Color(0.1, 0.1, 0.1, 0.75),
                    pixelOffset: new Cesium.Cartesian2(0, -16),
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    disableDepthTestDistance: Number.POSITIVE_INFINITY,
                    distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 20000000)
                },
                description: `地面站ID: ${gs.id}<br/>名称: ${displayName}<br/>纬度: ${gs.latitude_deg}<br/>经度: ${gs.longitude_deg}<br/>海拔: ${gs.elevation_m}m`
            });
            groundStationEntities.push(entity);
        });

        function applyDirectionFilter() {
            const northOnly = filterNorthOnlyEl.checked;
            const southOnly = filterSouthOnlyEl.checked;

            satelliteEntities.forEach((entity) => {
                if (northOnly && !southOnly) {
                    entity.show = entity.directionKey === 'northbound';
                } else if (southOnly && !northOnly) {
                    entity.show = entity.directionKey === 'southbound';
                } else if (northOnly && southOnly) {
                    entity.show = entity.directionKey === 'northbound' || entity.directionKey === 'southbound';
                } else {
                    entity.show = true;
                }
            });
            viewer.scene.requestRender();
        }

        function getDirectionAtTime(entity, time) {
            const currentPos = entity.position.getValue(time);
            if (!currentPos) {
                return 'unknown';
            }
            const nextTime = Cesium.JulianDate.addSeconds(time, 30, new Cesium.JulianDate());
            const nextPos = entity.position.getValue(nextTime);
            if (!nextPos) {
                return 'unknown';
            }

            const lat1 = Cesium.Math.toDegrees(Cesium.Cartographic.fromCartesian(currentPos).latitude);
            const lat2 = Cesium.Math.toDegrees(Cesium.Cartographic.fromCartesian(nextPos).latitude);
            const dLat = lat2 - lat1;
            if (dLat > 1e-6) {
                return 'northbound';
            }
            if (dLat < -1e-6) {
                return 'southbound';
            }
            return 'unknown';
        }

        function updateDirectionStylingAndCounts(currentTime) {
            let northboundCount = 0;
            let southboundCount = 0;
            let unknownDirectionCount = 0;

            satelliteEntities.forEach((entity) => {
                const direction = getDirectionAtTime(entity, currentTime);
                entity.directionKey = direction;

                if (direction === 'northbound') {
                    northboundCount += 1;
                    entity.point.outlineColor = Cesium.Color.CYAN;
                    entity.path.material = entity.baseColor.withAlpha(0.55);
                    if (showLabels) {
                        entity.label.text = entity.baseName + ' ↑';
                    }
                } else if (direction === 'southbound') {
                    southboundCount += 1;
                    entity.point.outlineColor = Cesium.Color.MAGENTA;
                    entity.path.material = new Cesium.PolylineDashMaterialProperty({
                        color: entity.baseColor.withAlpha(0.8),
                        dashLength: 12
                    });
                    if (showLabels) {
                        entity.label.text = entity.baseName + ' ↓';
                    }
                } else {
                    unknownDirectionCount += 1;
                    entity.point.outlineColor = Cesium.Color.WHITE;
                    entity.path.material = entity.baseColor.withAlpha(0.55);
                    if (showLabels) {
                        entity.label.text = entity.baseName;
                    }
                }

                entity.description = `卫星名称: ${entity.baseName}<br/>方向: ${direction}<br/>` +
                    `TLE Line 1: ${entity.tleLine1}<br/>` +
                    `TLE Line 2: ${entity.tleLine2}`;
            });

            document.getElementById('northboundCount').textContent = String(northboundCount);
            document.getElementById('southboundCount').textContent = String(southboundCount);
            document.getElementById('unknownDirectionCount').textContent = String(unknownDirectionCount);
        }

        filterNorthOnlyEl.addEventListener('change', applyDirectionFilter);
        filterSouthOnlyEl.addEventListener('change', applyDirectionFilter);

        viewer.clock.startTime = startTime.clone();
        viewer.clock.stopTime = stopTime.clone();
        viewer.clock.currentTime = startTime.clone();
        viewer.clock.multiplier = 60;
        viewer.clock.shouldAnimate = true;
        viewer.clock.clockRange = Cesium.ClockRange.LOOP_STOP;
        viewer.timeline.zoomTo(startTime, stopTime);

        viewer.clock.onTick.addEventListener(() => {
            const currentJulian = viewer.clock.currentTime;
            const current = Cesium.JulianDate.toDate(currentJulian);
            document.getElementById('currentTime').textContent = current.toUTCString();
            updateDirectionStylingAndCounts(currentJulian);
            applyDirectionFilter();
        });

        viewer.camera.setView({
            destination: Cesium.Rectangle.fromDegrees(70.0, 15.0, 140.0, 55.0)
        });

        if (satelliteEntities.length > 0) {
            viewer.zoomTo(viewer.entities);
        }

        updateDirectionStylingAndCounts(startTime);
        applyDirectionFilter();
        viewer.scene.requestRender();
        statusEl.textContent = `已加载 ${satelliteEntities.length} 颗，失败 ${failedCount} 颗`;
        console.log(`成功加载 ${satelliteEntities.length} 颗卫星，${groundStationEntities.length} 个地面站，失败 ${failedCount} 颗卫星。`);
    </script>
</body>
</html>
"""


def read_tle_file(file_path: Path):
    satellites = []
    lines = [line.strip() for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]

    i = 0
    auto_index = 1
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            name = f"SAT-{auto_index:05d}"
            tle_line1 = lines[i]
            tle_line2 = lines[i + 1]
            i += 2
            auto_index += 1
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            name = lines[i].replace(" ", "-")
            tle_line1 = lines[i + 1]
            tle_line2 = lines[i + 2]
            i += 3
        else:
            i += 1
            continue

        satellites.append(
            {
                "name": name,
                "tle_line1": tle_line1,
                "tle_line2": tle_line2,
            }
        )

    return satellites


def read_ground_stations_file(file_path: Path):
    ground_stations = []

    def _extract_city_name(name: str) -> str:
        text = name.strip()
        if text.startswith("City: ") and ";" in text:
            text = text.split(";", 1)[0].replace("City: ", "").strip()
        return text

    with file_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            if len(row) < 5:
                continue
            try:
                gs_id = int(row[0].strip())
                name = row[1].strip()
                latitude_deg = float(row[2].strip())
                longitude_deg = float(row[3].strip())
                elevation_m = float(row[4].strip())
            except ValueError:
                continue

            city_name = _extract_city_name(name)
            name_zh = CITY_NAME_ZH_MAP.get(city_name.lower(), city_name)

            ground_stations.append(
                {
                    "id": gs_id,
                    "name": name,
                    "name_zh": name_zh,
                    "latitude_deg": latitude_deg,
                    "longitude_deg": longitude_deg,
                    "elevation_m": elevation_m,
                }
            )
    return ground_stations


def cluster_orbits_by_raan(satellites, raan_threshold_deg: float):
    records = []
    for idx, sat in enumerate(satellites):
        try:
            parts = sat["tle_line2"].split()
            raan = float(parts[3]) % 360.0
            records.append((idx, raan))
        except (IndexError, ValueError, KeyError):
            sat["orbit_id"] = 0

    if not records:
        return

    records.sort(key=lambda item: item[1])
    clusters = [[records[0]]]
    for current in records[1:]:
        prev = clusters[-1][-1]
        if current[1] - prev[1] <= raan_threshold_deg:
            clusters[-1].append(current)
        else:
            clusters.append([current])

    if len(clusters) > 1:
        first_raan = clusters[0][0][1]
        last_raan = clusters[-1][-1][1]
        if first_raan + 360.0 - last_raan <= raan_threshold_deg:
            merged = clusters[-1] + clusters[0]
            clusters = [merged] + clusters[1:-1]

    def circular_mean_deg(values):
        x = sum(math.cos(math.radians(v)) for v in values)
        y = sum(math.sin(math.radians(v)) for v in values)
        return math.degrees(math.atan2(y, x)) % 360.0

    clusters = sorted(clusters, key=lambda c: circular_mean_deg([item[1] for item in c]))
    for orbit_id, cluster in enumerate(clusters):
        for sat_index, _ in cluster:
            satellites[sat_index]["orbit_id"] = orbit_id

    for sat in satellites:
        if "orbit_id" not in sat:
            sat["orbit_id"] = 0


def parse_tle_epoch_utc(tle_line1: str):
    try:
        epoch_field = tle_line1[18:32].strip()
        if len(epoch_field) < 5:
            return None
        yy = int(epoch_field[:2])
        day_of_year = float(epoch_field[2:])
        year = 2000 + yy if yy < 57 else 1900 + yy
        start_of_year = datetime(year, 1, 1, tzinfo=timezone.utc)
        return start_of_year + timedelta(days=day_of_year - 1)
    except (ValueError, IndexError):
        return None


def get_latest_tle_epoch_utc(satellites):
    latest = None
    for sat in satellites:
        epoch_dt = parse_tle_epoch_utc(sat["tle_line1"])
        if epoch_dt is None:
            continue
        if latest is None or epoch_dt > latest:
            latest = epoch_dt
    if latest is None:
        latest = datetime.now(timezone.utc)
    return latest


def generate_html(satellites, ground_stations, output_path: Path, duration_minutes: int, time_step_seconds: int):
    tle_start_time = get_latest_tle_epoch_utc(satellites)
    tle_start_time_iso = tle_start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    tle_start_time_label = tle_start_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    html_content = (
        HTML_TEMPLATE.replace("__SATELLITES_JSON__", json.dumps(satellites, ensure_ascii=False))
        .replace("__GROUND_STATIONS_JSON__", json.dumps(ground_stations, ensure_ascii=False))
        .replace("__SAT_COUNT__", str(len(satellites)))
        .replace("__GS_COUNT__", str(len(ground_stations)))
        .replace("__DURATION_MINUTES__", str(duration_minutes))
        .replace("__TIME_STEP_SECONDS__", str(time_step_seconds))
        .replace("__TLE_START_TIME_ISO__", tle_start_time_iso)
        .replace("__TLE_START_TIME_LABEL__", tle_start_time_label)
    )

    output_path.write_text(html_content, encoding="utf-8")
    print(f"生成成功：{output_path}")
    print(f"共处理卫星：{len(satellites)}")


def main():
    parser = argparse.ArgumentParser(description="TLE 轨道可视化 HTML 生成器")
    parser.add_argument("tle_file", nargs="?", default="shell_29.txt", help="输入 TLE 文件路径，默认 shell_29.txt")
    parser.add_argument("--output", default="satellites_visualization.html", help="输出 HTML 路径")
    parser.add_argument("--duration-minutes", type=int, default=60, help="轨迹时长（分钟），默认 60")
    parser.add_argument("--time-step-seconds", type=int, default=120, help="轨迹采样步长（秒），默认 120")
    parser.add_argument("--max-satellites", type=int, default=0, help="最多可视化卫星数，0 表示全部")
    parser.add_argument("--raan-threshold", type=float, default=2.0, help="按 RAAN 聚类轨道面的阈值（度），默认 2.0")
    parser.add_argument("--ground-stations", default=None, help="可选：地面站文件路径（basic 或 extended，读取前5列）")
    args = parser.parse_args()

    tle_path = Path(args.tle_file)
    if not tle_path.exists():
        print(f"错误：找不到输入文件 {tle_path}")
        return

    satellites = read_tle_file(tle_path)
    if not satellites:
        print("错误：未解析到有效 TLE 数据")
        return

    if args.max_satellites > 0:
        satellites = satellites[: args.max_satellites]

    cluster_orbits_by_raan(satellites, args.raan_threshold)

    ground_stations = []
    if args.ground_stations:
        gs_path = Path(args.ground_stations)
        if not gs_path.exists():
            print(f"错误：找不到地面站文件 {gs_path}")
            return
        ground_stations = read_ground_stations_file(gs_path)

    output_path = Path(args.output)
    if output_path.parent != Path(""):
        output_path.parent.mkdir(parents=True, exist_ok=True)

    generate_html(satellites, ground_stations, output_path, args.duration_minutes, args.time_step_seconds)


if __name__ == "__main__":
    main()
