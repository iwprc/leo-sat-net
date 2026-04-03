#!/usr/bin/env python3

import argparse
import json
import math
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import DefaultDict, Dict, List, Sequence, Tuple

from makeisl import START_TIME_UTC, parse_start_time, parse_three_line_tles


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ISL Connected Components Visualization</title>
    <style>
        :root {
            --bg: #07111f;
            --panel: rgba(7, 17, 31, 0.82);
            --panel-border: rgba(125, 176, 255, 0.22);
            --text: #edf4ff;
            --muted: #93a7c4;
            --accent: #5fd1ff;
            --accent-2: #ffc857;
        }

        html, body, #cesiumContainer {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: radial-gradient(circle at top, #123052 0%, #07111f 55%, #040913 100%);
            font-family: "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif;
        }

        #infoPanel {
            position: absolute;
            top: 12px;
            left: 12px;
            width: min(420px, calc(100vw - 24px));
            max-height: calc(100vh - 24px);
            overflow: auto;
            background: var(--panel);
            color: var(--text);
            border: 1px solid var(--panel-border);
            border-radius: 16px;
            backdrop-filter: blur(14px);
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
            z-index: 1000;
        }

        .panel-block {
            padding: 14px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }

        .panel-block:last-child {
            border-bottom: none;
        }

        .eyebrow {
            color: var(--accent);
            font-size: 11px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        h1 {
            margin: 0;
            font-size: 21px;
            font-weight: 700;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-top: 12px;
        }

        .summary-card {
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 10px 12px;
            background: rgba(255, 255, 255, 0.03);
        }

        .summary-label {
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 4px;
        }

        .summary-value {
            font-size: 18px;
            font-weight: 700;
        }

        .toolbar {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }

        button {
            border: 1px solid rgba(255, 255, 255, 0.14);
            background: rgba(255, 255, 255, 0.05);
            color: var(--text);
            border-radius: 999px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 12px;
        }

        button:hover {
            border-color: rgba(95, 209, 255, 0.5);
            background: rgba(95, 209, 255, 0.1);
        }

        .status {
            color: var(--accent-2);
            font-size: 12px;
            margin-top: 8px;
        }

        .component-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-top: 12px;
        }

        .component-card {
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 12px;
            background: rgba(255, 255, 255, 0.03);
        }

        .component-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }

        .component-title {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 700;
        }

        .swatch {
            width: 12px;
            height: 12px;
            border-radius: 999px;
            flex: 0 0 auto;
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.08);
        }

        .component-meta {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-top: 10px;
            color: var(--muted);
            font-size: 12px;
        }

        .component-actions {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
            font-size: 12px;
            color: var(--muted);
        }

        .component-actions input {
            accent-color: var(--accent);
        }

        #cesiumContainer canvas:focus {
            outline: none;
        }
    </style>
</head>
<body>
    <div id="cesiumContainer"></div>
    <div id="infoPanel">
        <div class="panel-block">
            <div class="eyebrow">Step 3 Visualization</div>
            <h1>Top ISL Connected Components</h1>
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="summary-label">可视化连通块</div>
                    <div class="summary-value" id="visualizedComponents"></div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">可视化卫星</div>
                    <div class="summary-value" id="visualizedSatellites"></div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">可视化 ISL</div>
                    <div class="summary-value" id="visualizedEdges"></div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">总连通块</div>
                    <div class="summary-value" id="totalComponents"></div>
                </div>
            </div>
            <div class="toolbar">
                <button id="showAll">显示全部</button>
                <button id="hideAll">隐藏全部</button>
                <button id="focusLargest">定位最大连通块</button>
            </div>
            <div class="status">快照时刻：<span id="snapshotTime"></span></div>
            <div class="status">状态：<span id="status">初始化中...</span></div>
        </div>
        <div class="panel-block">
            <div class="eyebrow">Graph Stats</div>
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="summary-label">总卫星</div>
                    <div class="summary-value" id="totalSatellites"></div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">总 ISL</div>
                    <div class="summary-value" id="totalIsls"></div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">非平凡连通块</div>
                    <div class="summary-value" id="nonTrivialComponents"></div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">孤立卫星</div>
                    <div class="summary-value" id="isolatedSatellites"></div>
                </div>
            </div>
        </div>
        <div class="panel-block">
            <div class="eyebrow">Components</div>
            <div class="component-list" id="componentList"></div>
        </div>
    </div>

    <script>
        const payload = __PAYLOAD_JSON__;

        async function loadScript(src) {
            return new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = src;
                script.async = true;
                script.onload = () => resolve(src);
                script.onerror = () => reject(new Error(`script load failed: ${src}`));
                document.head.appendChild(script);
            });
        }

        async function loadCss(href) {
            return new Promise((resolve, reject) => {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = href;
                link.onload = () => resolve(href);
                link.onerror = () => reject(new Error(`css load failed: ${href}`));
                document.head.appendChild(link);
            });
        }

        async function ensureDependencies(statusEl) {
            const cesiumCandidates = [
                {
                    label: 'jsdelivr',
                    script: 'https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/Cesium.js',
                    css: 'https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/Widgets/widgets.css',
                    base: 'https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/'
                },
                {
                    label: 'unpkg',
                    script: 'https://unpkg.com/cesium@1.107.1/Build/Cesium/Cesium.js',
                    css: 'https://unpkg.com/cesium@1.107.1/Build/Cesium/Widgets/widgets.css',
                    base: 'https://unpkg.com/cesium@1.107.1/Build/Cesium/'
                }
            ];

            const satelliteCandidates = [
                { label: 'jsdelivr', script: 'https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js' },
                { label: 'unpkg', script: 'https://unpkg.com/satellite.js/dist/satellite.min.js' }
            ];

            let cesiumBaseUrl = 'https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/';
            if (typeof Cesium === 'undefined') {
                for (const candidate of cesiumCandidates) {
                    try {
                        statusEl.textContent = `正在加载 Cesium（${candidate.label}）...`;
                        await loadCss(candidate.css);
                        await loadScript(candidate.script);
                        if (typeof Cesium !== 'undefined') {
                            cesiumBaseUrl = candidate.base;
                            break;
                        }
                    } catch (error) {
                        console.warn(error);
                    }
                }
            }

            if (typeof Cesium === 'undefined') {
                statusEl.textContent = 'Cesium 加载失败';
                return null;
            }

            if (typeof satellite === 'undefined') {
                for (const candidate of satelliteCandidates) {
                    try {
                        statusEl.textContent = `正在加载 satellite.js（${candidate.label}）...`;
                        await loadScript(candidate.script);
                        if (typeof satellite !== 'undefined') {
                            break;
                        }
                    } catch (error) {
                        console.warn(error);
                    }
                }
            }

            if (typeof satellite === 'undefined') {
                statusEl.textContent = 'satellite.js 加载失败';
                return null;
            }

            return { cesiumBaseUrl };
        }

        function componentColor(index, total) {
            const hue = total <= 1 ? 0.0 : index / total;
            return Cesium.Color.fromHsl(hue, 0.82, 0.58, 1.0);
        }

        function formatNumber(value) {
            return new Intl.NumberFormat('zh-CN').format(value);
        }

        function computeCartesianFromTle(tle1, tle2, jsDate) {
            const satrec = satellite.twoline2satrec(tle1, tle2);
            const pv = satellite.propagate(satrec, jsDate);
            if (!pv || !pv.position) {
                return null;
            }
            const gmst = satellite.gstime(jsDate);
            const ecf = satellite.eciToEcf(pv.position, gmst);
            return new Cesium.Cartesian3(ecf.x * 1000, ecf.y * 1000, ecf.z * 1000);
        }

        (async () => {
            document.getElementById('snapshotTime').textContent = payload.snapshot_time_utc;
            document.getElementById('visualizedComponents').textContent = formatNumber(payload.top_components.length);
            document.getElementById('visualizedSatellites').textContent = formatNumber(payload.visualized_satellite_count);
            document.getElementById('visualizedEdges').textContent = formatNumber(payload.visualized_isl_count);
            document.getElementById('totalComponents').textContent = formatNumber(payload.num_components_total);
            document.getElementById('totalSatellites').textContent = formatNumber(payload.num_satellites_total);
            document.getElementById('totalIsls').textContent = formatNumber(payload.num_isls_total);
            document.getElementById('nonTrivialComponents').textContent = formatNumber(payload.num_nontrivial_components);
            document.getElementById('isolatedSatellites').textContent = formatNumber(payload.num_isolated_satellites);

            const statusEl = document.getElementById('status');
            const deps = await ensureDependencies(statusEl);
            if (!deps) {
                return;
            }

            Cesium.buildModuleUrl.setBaseUrl(deps.cesiumBaseUrl);

            const viewer = new Cesium.Viewer('cesiumContainer', {
                timeline: false,
                animation: false,
                baseLayerPicker: false,
                geocoder: false,
                homeButton: false,
                sceneModePicker: true,
                navigationHelpButton: false,
                fullscreenButton: true,
                terrainProvider: new Cesium.EllipsoidTerrainProvider(),
                imageryProvider: new Cesium.UrlTemplateImageryProvider({
                    url: 'https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/Assets/Textures/NaturalEarthII/{z}/{x}/{reverseY}.jpg',
                    maximumLevel: 2,
                    credit: 'Natural Earth II via Cesium'
                })
            });

            viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#13263f');
            viewer.scene.globe.enableLighting = false;
            viewer.scene.globe.depthTestAgainstTerrain = true;
            viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#040913');
            viewer.scene.skyAtmosphere.show = false;
            viewer.scene.skyBox.show = false;
            viewer.scene.fog.enabled = false;
            viewer._cesiumWidget._creditContainer.style.display = 'none';

            const jsDate = new Date(payload.snapshot_time_utc);
            const satPositionMap = new Map();
            const componentState = new Map();
            const componentBounds = new Map();

            function classifyDirection(currentCartesian, nextCartesian) {
                if (!currentCartesian || !nextCartesian) {
                    return 'unknown';
                }
                const currentCartographic = Cesium.Cartographic.fromCartesian(currentCartesian);
                const nextCartographic = Cesium.Cartographic.fromCartesian(nextCartesian);
                if (!currentCartographic || !nextCartographic) {
                    return 'unknown';
                }
                const currentLatitude = Cesium.Math.toDegrees(currentCartographic.latitude);
                const nextLatitude = Cesium.Math.toDegrees(nextCartographic.latitude);
                return nextLatitude >= currentLatitude ? 'north' : 'south';
            }

            function isSatelliteVisible(state, satelliteRecord) {
                if (!state.visible) {
                    return false;
                }
                if (satelliteRecord.direction === 'north') {
                    return state.showNorth;
                }
                if (satelliteRecord.direction === 'south') {
                    return state.showSouth;
                }
                return state.showNorth || state.showSouth;
            }

            function syncComponentVisibility(rank) {
                const state = componentState.get(rank);
                if (!state) {
                    return;
                }
                const visibleBySid = new Map();
                for (const satelliteRecord of state.satellites) {
                    const visible = isSatelliteVisible(state, satelliteRecord);
                    satelliteRecord.entity.show = visible;
                    visibleBySid.set(satelliteRecord.sid, visible);
                }
                for (const edgeRecord of state.edges) {
                    edgeRecord.entity.show = Boolean(visibleBySid.get(edgeRecord.a) && visibleBySid.get(edgeRecord.b));
                }
            }

            payload.top_components.forEach((component, index) => {
                componentState.set(component.rank, {
                    satellites: [],
                    edges: [],
                    visible: true,
                    showNorth: true,
                    showSouth: true,
                    northCount: 0,
                    southCount: 0,
                    unknownCount: 0,
                    color: componentColor(index, payload.top_components.length),
                });
            });

            statusEl.textContent = '正在传播卫星位置...';
            for (const component of payload.top_components) {
                const state = componentState.get(component.rank);
                for (const sat of component.satellites) {
                    const cartesian = computeCartesianFromTle(sat.tle1, sat.tle2, jsDate);
                    if (!cartesian) {
                        continue;
                    }
                    const nextCartesian = computeCartesianFromTle(sat.tle1, sat.tle2, new Date(jsDate.getTime() + 30 * 1000));
                    const direction = classifyDirection(cartesian, nextCartesian);
                    if (direction === 'north') {
                        state.northCount += 1;
                    } else if (direction === 'south') {
                        state.southCount += 1;
                    } else {
                        state.unknownCount += 1;
                    }
                    satPositionMap.set(sat.sid, cartesian);
                    const entity = viewer.entities.add({
                        position: cartesian,
                        point: {
                            pixelSize: 7,
                            color: state.color,
                            outlineColor: Cesium.Color.WHITE.withAlpha(0.9),
                            outlineWidth: 1.2,
                        },
                        description: `卫星ID: ${sat.sid}<br/>名称: ${sat.name}<br/>连通块: #${component.rank}<br/>方向: ${direction === 'north' ? '北上' : direction === 'south' ? '南下' : '未知'}<br/>半长轴: ${sat.semi_major_axis_km.toFixed(3)} km<br/>倾角: ${sat.inclination_deg.toFixed(3)}°<br/>RAAN: ${sat.raan_deg.toFixed(3)}°`,
                    });
                    state.satellites.push({ sid: sat.sid, entity, direction });
                }
            }

            statusEl.textContent = '正在构建 ISL 线段...';
            for (const component of payload.top_components) {
                const state = componentState.get(component.rank);
                const points = [];
                for (const sat of component.satellites) {
                    const cartesian = satPositionMap.get(sat.sid);
                    if (cartesian) {
                        points.push(cartesian);
                    }
                }
                componentBounds.set(component.rank, points);
                for (const edge of component.edges) {
                    const start = satPositionMap.get(edge[0]);
                    const end = satPositionMap.get(edge[1]);
                    if (!start || !end) {
                        continue;
                    }
                    const edgeEntity = viewer.entities.add({
                        polyline: {
                            positions: [start, end],
                            width: 1.35,
                            material: state.color.withAlpha(0.38),
                            clampToGround: false,
                        },
                    });
                    state.edges.push({ a: edge[0], b: edge[1], entity: edgeEntity });
                }
                syncComponentVisibility(component.rank);
            }

            function setComponentVisibility(rank, visible) {
                const state = componentState.get(rank);
                if (!state) {
                    return;
                }
                state.visible = visible;
                syncComponentVisibility(rank);
                const checkbox = document.getElementById(`toggle-${rank}`);
                if (checkbox) {
                    checkbox.checked = visible;
                }
            }

            function setDirectionalVisibility(rank, direction, visible) {
                const state = componentState.get(rank);
                if (!state) {
                    return;
                }
                if (direction === 'north') {
                    state.showNorth = visible;
                } else if (direction === 'south') {
                    state.showSouth = visible;
                }
                syncComponentVisibility(rank);
            }

            function flyToComponent(rank) {
                const points = componentBounds.get(rank) || [];
                if (!points.length) {
                    return;
                }
                const sphere = Cesium.BoundingSphere.fromPoints(points);
                viewer.camera.flyToBoundingSphere(sphere, { duration: 1.2, offset: new Cesium.HeadingPitchRange(0.0, -0.55, sphere.radius * 2.8) });
            }

            document.getElementById('showAll').addEventListener('click', () => {
                for (const component of payload.top_components) {
                    setComponentVisibility(component.rank, true);
                }
            });

            document.getElementById('hideAll').addEventListener('click', () => {
                for (const component of payload.top_components) {
                    setComponentVisibility(component.rank, false);
                }
            });

            document.getElementById('focusLargest').addEventListener('click', () => {
                if (payload.top_components.length > 0) {
                    flyToComponent(payload.top_components[0].rank);
                }
            });

            const componentList = document.getElementById('componentList');
            payload.top_components.forEach((component, index) => {
                const state = componentState.get(component.rank);
                const colorCss = state.color.toCssColorString();
                const card = document.createElement('div');
                card.className = 'component-card';
                card.innerHTML = `
                    <div class="component-header">
                        <div class="component-title"><span class="swatch" style="background:${colorCss}"></span>连通块 #${component.rank}</div>
                        <button type="button" id="focus-${component.rank}">定位</button>
                    </div>
                    <div class="component-meta">
                        <div>卫星: ${formatNumber(component.satellite_count)}</div>
                        <div>ISL: ${formatNumber(component.edge_count)}</div>
                        <div>平均度: ${component.average_degree.toFixed(3)}</div>
                        <div>密度: ${component.density.toFixed(5)}</div>
                        <div>平均半长轴: ${component.mean_semi_major_axis_km.toFixed(3)} km</div>
                        <div>平均倾角: ${component.mean_inclination_deg.toFixed(3)}°</div>
                    </div>
                    <div class="component-actions">
                        <label><input id="toggle-${component.rank}" type="checkbox" checked> 显示</label>
                        <label><input id="north-${component.rank}" type="checkbox" checked> 北上 (${formatNumber(state.northCount)})</label>
                        <label><input id="south-${component.rank}" type="checkbox" checked> 南下 (${formatNumber(state.southCount)})</label>
                        <span>卫星 ID 范围: ${component.min_satellite_id} - ${component.max_satellite_id}</span>
                    </div>
                `;
                componentList.appendChild(card);

                card.querySelector(`#toggle-${component.rank}`).addEventListener('change', (event) => {
                    setComponentVisibility(component.rank, event.target.checked);
                });
                card.querySelector(`#north-${component.rank}`).addEventListener('change', (event) => {
                    setDirectionalVisibility(component.rank, 'north', event.target.checked);
                });
                card.querySelector(`#south-${component.rank}`).addEventListener('change', (event) => {
                    setDirectionalVisibility(component.rank, 'south', event.target.checked);
                });
                card.querySelector(`#focus-${component.rank}`).addEventListener('click', () => {
                    flyToComponent(component.rank);
                });

                if (index === 0) {
                    setTimeout(() => flyToComponent(component.rank), 100);
                }
            });

            statusEl.textContent = '加载完成';
        })();
    </script>
</body>
</html>
"""


def read_isls(isls_path: Path, num_satellites: int) -> Tuple[List[Tuple[int, int]], List[List[int]]]:
    edges: List[Tuple[int, int]] = []
    adjacency = [[] for _ in range(num_satellites)]
    seen = set()

    with isls_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split()
            if len(parts) != 2:
                raise ValueError(f"Invalid ISL line {line_number}: {stripped}")
            left = int(parts[0])
            right = int(parts[1])
            if left < 0 or right < 0 or left >= num_satellites or right >= num_satellites:
                raise ValueError(f"ISL line {line_number} references a non-existent satellite")
            if right <= left:
                raise ValueError(f"ISL line {line_number} must satisfy left < right")
            edge = (left, right)
            if edge in seen:
                raise ValueError(f"Duplicate ISL at line {line_number}: {edge}")
            seen.add(edge)
            edges.append(edge)
            adjacency[left].append(right)
            adjacency[right].append(left)

    return edges, adjacency


def compute_components(adjacency: Sequence[Sequence[int]]) -> Tuple[List[Dict], List[int]]:
    visited = [False] * len(adjacency)
    component_of = [-1] * len(adjacency)
    components: List[Dict] = []

    for satellite_id in range(len(adjacency)):
        if visited[satellite_id]:
            continue
        queue = deque([satellite_id])
        visited[satellite_id] = True
        members: List[int] = []
        degree_sum = 0

        while queue:
            current = queue.popleft()
            component_of[current] = len(components)
            members.append(current)
            degree_sum += len(adjacency[current])
            for neighbor in adjacency[current]:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    queue.append(neighbor)

        components.append(
            {
                "component_id": len(components),
                "satellite_ids": sorted(members),
                "satellite_count": len(members),
                "edge_count": degree_sum // 2,
            }
        )

    return components, component_of


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def circular_mean_deg(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    x = sum(math.cos(math.radians(value)) for value in values)
    y = sum(math.sin(math.radians(value)) for value in values)
    return math.degrees(math.atan2(y, x)) % 360.0


def build_component_statistics(
    satellites,
    components: Sequence[Dict],
    component_edges: Dict[int, List[Tuple[int, int]]],
) -> List[Dict]:
    stats: List[Dict] = []
    for component in components:
        member_ids = component["satellite_ids"]
        member_satellites = [satellites[satellite_id] for satellite_id in member_ids]
        semi_major_axes = [sat.semi_major_axis_km for sat in member_satellites]
        inclinations = [sat.inclination_deg for sat in member_satellites]
        raans = [sat.raan_deg for sat in member_satellites]
        edge_count = component["edge_count"]
        satellite_count = component["satellite_count"]
        density = 0.0
        if satellite_count > 1:
            density = (2.0 * edge_count) / (satellite_count * (satellite_count - 1))

        stats.append(
            {
                "component_id": component["component_id"],
                "satellite_ids": member_ids,
                "edges": component_edges.get(component["component_id"], []),
                "satellite_count": satellite_count,
                "edge_count": edge_count,
                "average_degree": (2.0 * edge_count / satellite_count) if satellite_count else 0.0,
                "density": density,
                "min_satellite_id": member_ids[0],
                "max_satellite_id": member_ids[-1],
                "mean_semi_major_axis_km": mean(semi_major_axes),
                "min_semi_major_axis_km": min(semi_major_axes),
                "max_semi_major_axis_km": max(semi_major_axes),
                "mean_inclination_deg": mean(inclinations),
                "min_inclination_deg": min(inclinations),
                "max_inclination_deg": max(inclinations),
                "mean_raan_deg": circular_mean_deg(raans),
                "min_raan_deg": min(raans),
                "max_raan_deg": max(raans),
            }
        )

    stats.sort(key=lambda item: (-item["satellite_count"], -item["edge_count"], item["min_satellite_id"]))
    for rank, item in enumerate(stats, start=1):
        item["rank"] = rank
    return stats


def serialize_component_summary(component: Dict) -> Dict:
    return {
        "rank": component["rank"],
        "component_id": component["component_id"],
        "satellite_count": component["satellite_count"],
        "edge_count": component["edge_count"],
        "average_degree": component["average_degree"],
        "density": component["density"],
        "min_satellite_id": component["min_satellite_id"],
        "max_satellite_id": component["max_satellite_id"],
        "mean_semi_major_axis_km": component["mean_semi_major_axis_km"],
        "min_semi_major_axis_km": component["min_semi_major_axis_km"],
        "max_semi_major_axis_km": component["max_semi_major_axis_km"],
        "mean_inclination_deg": component["mean_inclination_deg"],
        "min_inclination_deg": component["min_inclination_deg"],
        "max_inclination_deg": component["max_inclination_deg"],
        "mean_raan_deg": component["mean_raan_deg"],
        "min_raan_deg": component["min_raan_deg"],
        "max_raan_deg": component["max_raan_deg"],
    }


def build_stats_payload(
    component_stats: Sequence[Dict],
    top_k: int,
    snapshot_time_utc: datetime,
    num_satellites: int,
    all_edge_count: int,
) -> Dict:
    top_component_summaries = [serialize_component_summary(component) for component in component_stats[:top_k]]

    return {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_time_utc": snapshot_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "num_satellites_total": num_satellites,
        "num_isls_total": all_edge_count,
        "num_components_total": len(component_stats),
        "num_nontrivial_components": sum(1 for item in component_stats if item["edge_count"] > 0),
        "num_isolated_satellites": sum(1 for item in component_stats if item["satellite_count"] == 1 and item["edge_count"] == 0),
        "visualized_satellite_count": sum(item["satellite_count"] for item in top_component_summaries),
        "visualized_isl_count": sum(item["edge_count"] for item in top_component_summaries),
        "top_components": top_component_summaries,
    }


def build_visualization_payload(
    satellites,
    component_stats: Sequence[Dict],
    stats_payload: Dict,
) -> Dict:
    top_components = []
    for component in component_stats[: len(stats_payload["top_components"])]:
        member_satellites = []
        for satellite_id in component["satellite_ids"]:
            satellite = satellites[satellite_id]
            member_satellites.append(
                {
                    "sid": satellite.sid,
                    "name": satellite.name,
                    "tle1": satellite.tle1,
                    "tle2": satellite.tle2,
                    "semi_major_axis_km": satellite.semi_major_axis_km,
                    "inclination_deg": satellite.inclination_deg,
                    "raan_deg": satellite.raan_deg,
                }
            )

        top_components.append(
            {
                **serialize_component_summary(component),
                "satellites": member_satellites,
                "edges": component["edges"],
            }
        )

    return {
        **stats_payload,
        "top_components": top_components,
    }


def write_html(output_path: Path, payload: Dict) -> None:
    html = HTML_TEMPLATE.replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=False))
    output_path.write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize the largest ISL connected components in Cesium.")
    parser.add_argument(
        "--input-tle",
        type=Path,
        default=Path(__file__).with_name("starlink-TLE-20260403.txt"),
        help="Input 3-line TLE file.",
    )
    parser.add_argument(
        "--input-isls",
        type=Path,
        default=Path(__file__).with_name("isls.txt"),
        help="Input ISL file.",
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        default=Path(__file__).with_name("vizisl_top10.html"),
        help="Output HTML file.",
    )
    parser.add_argument(
        "--stats-output",
        type=Path,
        default=Path(__file__).with_name("vizisl_top10_stats.json"),
        help="Output lightweight JSON statistics file.",
    )
    parser.add_argument(
        "--data-output",
        type=Path,
        default=Path(__file__).with_name("vizisl_top10_data.json"),
        help="Output detailed JSON visualization data file.",
    )
    parser.add_argument(
        "--start-time",
        default=START_TIME_UTC.strftime("%Y-%m-%dT%H:%M:%SZ"),
        help="Visualization snapshot time in UTC.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of connected components to visualize.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top_k <= 0:
        raise ValueError("top-k must be positive")

    satellites = parse_three_line_tles(args.input_tle)
    edges, adjacency = read_isls(args.input_isls, len(satellites))
    components, component_of = compute_components(adjacency)

    component_edges: DefaultDict[int, List[Tuple[int, int]]] = defaultdict(list)
    for left, right in edges:
        component_id = component_of[left]
        component_edges[component_id].append((left, right))

    component_stats = build_component_statistics(satellites, components, component_edges)
    stats_payload = build_stats_payload(
        component_stats,
        args.top_k,
        parse_start_time(args.start_time),
        len(satellites),
        len(edges),
    )
    top_component_stats = component_stats[: args.top_k]
    visualization_payload = build_visualization_payload(
        satellites,
        top_component_stats,
        stats_payload,
    )

    args.stats_output.write_text(json.dumps(stats_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.data_output.write_text(json.dumps(visualization_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_html(args.html_output, visualization_payload)

    print(f"total_satellites={stats_payload['num_satellites_total']}")
    print(f"total_isls={stats_payload['num_isls_total']}")
    print(f"components={stats_payload['num_components_total']}")
    print(f"nontrivial_components={stats_payload['num_nontrivial_components']}")
    print(f"isolated_satellites={stats_payload['num_isolated_satellites']}")
    for component in stats_payload["top_components"]:
        print(
            f"component_rank={component['rank']} satellites={component['satellite_count']} "
            f"isls={component['edge_count']} avg_degree={component['average_degree']:.3f}"
        )
    print(f"html_output={args.html_output}")
    print(f"stats_output={args.stats_output}")
    print(f"data_output={args.data_output}")


if __name__ == "__main__":
    main()