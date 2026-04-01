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
import re
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
        <div>用户数量：__USER_COUNT__</div>
        <div>POP数量：__POP_COUNT__</div>
        <div>轨迹时长：__DURATION_MINUTES__ 分钟</div>
        <div>采样步长：__TIME_STEP_SECONDS__ 秒</div>
        <div>TLE 起始时刻：<span id="tleEpochTime">__TLE_START_TIME_LABEL__</span></div>
        <div style="margin-top: 6px;">
            <label style="display: block;"><input type="checkbox" id="showGroundStations" checked> 显示地面站</label>
            <label style="display: block;"><input type="checkbox" id="showUsers" checked> 显示用户分布</label>
            <label style="display: block;"><input type="checkbox" id="showPops" checked> 显示POP</label>
        </div>
        <div style="margin-top: 6px;">壳层统计：<span id="shellSummary">加载中...</span></div>
        <div style="margin-top: 6px;">壳层显示（每层可选北上/南下）：</div>
        <div id="shellControls" style="margin-top: 6px; max-height: 220px; overflow: auto; border: 1px solid rgba(255,255,255,0.15); padding: 6px; border-radius: 6px;"></div>
        <div>图例：不同轨道=不同颜色；北上=青色描边；南下=洋红虚线</div>
        <div>状态：<span id="status">初始化中...</span></div>
        <div>时间：<span id="currentTime"></span></div>
        <div>点击卫星查看详情</div>
    </div>

    <script>
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

            let cesiumLoaded = typeof Cesium !== 'undefined';
            let cesiumBaseUrl = 'https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/';
            if (!cesiumLoaded) {
                for (const candidate of cesiumCandidates) {
                    try {
                        statusEl.textContent = `正在加载 Cesium（${candidate.label}）...`;
                        await loadCss(candidate.css);
                        await loadScript(candidate.script);
                        if (typeof Cesium !== 'undefined') {
                            cesiumLoaded = true;
                            cesiumBaseUrl = candidate.base;
                            break;
                        }
                    } catch (error) {
                        console.warn(`Cesium CDN ${candidate.label} 加载失败`, error);
                    }
                }
            }

            if (!cesiumLoaded) {
                statusEl.textContent = 'Cesium 加载失败（已尝试 jsdelivr/unpkg）';
                return null;
            }

            const satelliteCandidates = [
                { label: 'jsdelivr', script: 'https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js' },
                { label: 'unpkg', script: 'https://unpkg.com/satellite.js/dist/satellite.min.js' }
            ];

            let satelliteLoaded = typeof satellite !== 'undefined';
            if (!satelliteLoaded) {
                for (const candidate of satelliteCandidates) {
                    try {
                        statusEl.textContent = `正在加载 satellite.js（${candidate.label}）...`;
                        await loadScript(candidate.script);
                        if (typeof satellite !== 'undefined') {
                            satelliteLoaded = true;
                            break;
                        }
                    } catch (error) {
                        console.warn(`satellite.js CDN ${candidate.label} 加载失败`, error);
                    }
                }
            }

            if (!satelliteLoaded) {
                statusEl.textContent = 'satellite.js 加载失败（已尝试 jsdelivr/unpkg）';
                return null;
            }

            return { cesiumBaseUrl };
        }

        (async () => {
        const statusEl = document.getElementById('status');
        const deps = await ensureDependencies(statusEl);
        if (!deps) {
            return;
        }

        Cesium.buildModuleUrl.setBaseUrl(deps.cesiumBaseUrl);

        const viewer = new Cesium.Viewer('cesiumContainer', {
            timeline: true,
            animation: true,
            baseLayerPicker: false,
            geocoder: false,
            homeButton: true,
            sceneModePicker: true,
            navigationHelpButton: false,
            fullscreenButton: true,
            sceneMode: Cesium.SceneMode.SCENE3D,
            imageryProvider: new Cesium.UrlTemplateImageryProvider({
                url: 'https://cdn.jsdelivr.net/npm/cesium@1.107.1/Build/Cesium/Assets/Textures/NaturalEarthII/{z}/{x}/{reverseY}.jpg',
                maximumLevel: 2,
                credit: 'Natural Earth II via Cesium'
            }),
            terrainProvider: new Cesium.EllipsoidTerrainProvider()
        });

        viewer.scene.globe.show = true;
        viewer.scene.globe.translucency.enabled = false;
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#223344');
        viewer.scene.globe.enableLighting = false;
        viewer.scene.globe.depthTestAgainstTerrain = false;
        viewer.scene.skyAtmosphere.show = false;
        viewer.scene.skyBox.show = false;
        viewer.scene.fog.enabled = false;
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0a0f1f');
        viewer.scene.screenSpaceCameraController.enableTranslate = true;
        viewer.scene.screenSpaceCameraController.enableZoom = true;
        viewer.scene.screenSpaceCameraController.enableRotate = true;
        viewer.scene.screenSpaceCameraController.enableTilt = true;
        viewer.scene.screenSpaceCameraController.enableLook = true;
        viewer.scene.screenSpaceCameraController.inertiaTranslate = 0.85;
        viewer.scene.screenSpaceCameraController.inertiaZoom = 0.8;
        viewer._cesiumWidget._creditContainer.style.display = 'none';
        statusEl.textContent = '正在计算轨道...（底图: NaturalEarthII）';

        function setNorthUpTopDownView() {
            viewer.camera.setView({
                destination: Cesium.Rectangle.fromDegrees(70.0, 15.0, 140.0, 55.0),
                orientation: {
                    heading: 0.0,
                    pitch: Cesium.Math.toRadians(-90.0),
                    roll: 0.0
                }
            });
        }

        // Keep "north-up" as the default/home perspective.
        if (viewer.homeButton && viewer.homeButton.viewModel) {
            viewer.homeButton.viewModel.command.beforeExecute.addEventListener((evt) => {
                evt.cancel = true;
                setNorthUpTopDownView();
            });
        }

        const rawSatellites = __SATELLITES_JSON__;
        const rawGroundStations = __GROUND_STATIONS_JSON__;
        const rawUsers = __USERS_JSON__;
        const rawPops = __POPS_JSON__;
        const shellSummary = __SHELL_SUMMARY_JSON__;
        const durationMinutes = __DURATION_MINUTES__;
        const timeStepInSeconds = __TIME_STEP_SECONDS__;
        const tleStartTime = Cesium.JulianDate.fromIso8601('__TLE_START_TIME_ISO__');
        const showGroundStationsEl = document.getElementById('showGroundStations');
        const showUsersEl = document.getElementById('showUsers');
        const showPopsEl = document.getElementById('showPops');
        const shellSummaryEl = document.getElementById('shellSummary');
        const shellControlsEl = document.getElementById('shellControls');

        // shellLabel -> { showShell: bool, showNorth: bool, showSouth: bool }
        const shellVisibility = new Map();

        function getShellKeyFromSatellite(satOrEntity) {
            const key = satOrEntity && (satOrEntity.shell_label || satOrEntity.shellLabel);
            return (typeof key === 'string' && key.length) ? key : 'unknown';
        }

        function ensureShellVisibility(key) {
            if (!shellVisibility.has(key)) {
                shellVisibility.set(key, { showShell: true, showNorth: true, showSouth: true });
            }
            return shellVisibility.get(key);
        }

        const orbitColorCache = new Map();

        function getOrbitColor(orbitId) {
            const normalizedOrbitId = Number.isInteger(orbitId) && orbitId >= 0 ? orbitId : 0;
            if (!orbitColorCache.has(normalizedOrbitId)) {
                const hue = ((normalizedOrbitId * 47) % 360) / 360.0;
                const color = Cesium.Color.fromHsl(hue, 0.85, 0.55);
                orbitColorCache.set(normalizedOrbitId, color);
            }
            return orbitColorCache.get(normalizedOrbitId);
        }

        const startTime = tleStartTime;
        const stopTime = Cesium.JulianDate.addSeconds(startTime, durationMinutes * 60, new Cesium.JulianDate());

        const satelliteEntities = [];
        const groundStationEntities = [];
        const userEntities = [];
        const popEntities = [];
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

                const shellId = Number.isInteger(sat.shell_id) ? sat.shell_id : 0;
                const orbitId = Number.isInteger(sat.orbit_id) ? sat.orbit_id : 0;
                const color = getOrbitColor(orbitId);
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
                    description: `卫星名称: ${sat.name}<br/>壳层: ${sat.shell_label || 'unknown'}<br/>轨道面: ${orbitId}<br/>方向: unknown<br/>TLE Line 1: ${sat.tle_line1}<br/>TLE Line 2: ${sat.tle_line2}`
                });

                entity.baseName = sat.name;
                entity.baseColor = color;
                entity.shellLabel = sat.shell_label || 'unknown';
                entity.orbitId = orbitId;
                entity.directionKey = 'unknown';
                entity.tleLine1 = sat.tle_line1;
                entity.tleLine2 = sat.tle_line2;

                satelliteEntities.push(entity);
            } catch (error) {
                failedCount += 1;
                console.error(`解析卫星 ${sat.name} 失败:`, error);
            }
        });

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
                    disableDepthTestDistance: 0
                },
                label: {
                    text: displayName,
                    font: '12px sans-serif',
                    show: false,
                    showBackground: true,
                    backgroundColor: new Cesium.Color(0.1, 0.1, 0.1, 0.75),
                    pixelOffset: new Cesium.Cartesian2(0, -16),
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    disableDepthTestDistance: 0,
                    distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 20000000)
                },
                description: `地面站ID: ${gs.id}<br/>名称: ${displayName}<br/>纬度: ${gs.latitude_deg}<br/>经度: ${gs.longitude_deg}<br/>海拔: ${gs.elevation_m}m`
            });
            groundStationEntities.push(entity);
        });

        const showUserLabels = rawUsers.length <= 150;
        rawUsers.forEach((user) => {
            const position = Cesium.Cartesian3.fromDegrees(user.longitude_deg, user.latitude_deg, 0);
            const entity = viewer.entities.add({
                name: user.name,
                position,
                point: {
                    pixelSize: 4,
                    color: Cesium.Color.LIME,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 0.8,
                    disableDepthTestDistance: 0
                },
                label: {
                    text: user.name,
                    font: '11px sans-serif',
                    show: showUserLabels,
                    showBackground: true,
                    backgroundColor: new Cesium.Color(0.05, 0.15, 0.05, 0.75),
                    pixelOffset: new Cesium.Cartesian2(0, -12),
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    disableDepthTestDistance: 0,
                    distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 12000000)
                },
                description: `用户: ${user.name}<br/>纬度: ${user.latitude_deg}<br/>经度: ${user.longitude_deg}<br/>权重: ${user.weight}`
            });
            userEntities.push(entity);
        });

        const showPopLabels = rawPops.length <= 120;
        rawPops.forEach((pop) => {
            const position = Cesium.Cartesian3.fromDegrees(pop.longitude_deg, pop.latitude_deg, 0);
            const entity = viewer.entities.add({
                name: `POP-${pop.name}`,
                position,
                point: {
                    pixelSize: 7,
                    color: Cesium.Color.ORANGE,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 1.0,
                    disableDepthTestDistance: 0
                },
                label: {
                    text: pop.name,
                    font: '11px sans-serif',
                    show: showPopLabels,
                    showBackground: true,
                    backgroundColor: new Cesium.Color(0.2, 0.12, 0.02, 0.75),
                    pixelOffset: new Cesium.Cartesian2(0, -12),
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    disableDepthTestDistance: 0,
                    distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 15000000)
                },
                description: `POP: ${pop.name}<br/>纬度: ${pop.latitude_deg}<br/>经度: ${pop.longitude_deg}`
            });
            popEntities.push(entity);
        });

        function renderShellSummary() {
            if (!Array.isArray(shellSummary) || shellSummary.length === 0) {
                shellSummaryEl.textContent = '无';
                return;
            }
            shellSummaryEl.textContent = shellSummary
                .map((item) => {
                    const oc = (typeof item.orbit_count === 'number') ? `, 轨道=${item.orbit_count}` : '';
                    return `${item.label}: ${item.count}${oc}`;
                })
                .join(' | ');
        }

        function renderShellControls() {
            if (!shellControlsEl) {
                return;
            }
            shellControlsEl.innerHTML = '';
            if (!Array.isArray(shellSummary) || shellSummary.length === 0) {
                shellControlsEl.textContent = '无';
                return;
            }

            shellSummary.forEach((item, idx) => {
                const label = (item && item.label) ? String(item.label) : `Shell-${idx}`;
                const count = (item && typeof item.count === 'number') ? item.count : 0;
                const v = ensureShellVisibility(label);

                const row = document.createElement('div');
                row.style.display = 'block';
                row.style.padding = '3px 0';
                row.style.borderBottom = '1px solid rgba(255,255,255,0.08)';

                const shellIdSafe = label.replace(/[^a-zA-Z0-9_-]/g, '_');
                const shellCbId = `shellShow_${shellIdSafe}`;
                const northCbId = `shellNorth_${shellIdSafe}`;
                const southCbId = `shellSouth_${shellIdSafe}`;

                row.innerHTML = `
                    <label style="display:block; cursor:pointer;">
                        <input type="checkbox" id="${shellCbId}" ${v.showShell ? 'checked' : ''}>
                        <span>${label}</span>
                        <span style="opacity:0.85;">（${count}）</span>
                    </label>
                    <div style="margin-left: 18px; opacity:0.95;">
                        <label style="margin-right: 10px; cursor:pointer;"><input type="checkbox" id="${northCbId}" ${v.showNorth ? 'checked' : ''}> 北上</label>
                        <label style="margin-right: 10px; cursor:pointer;"><input type="checkbox" id="${southCbId}" ${v.showSouth ? 'checked' : ''}> 南下</label>
                    </div>
                `;

                shellControlsEl.appendChild(row);

                const shellCb = document.getElementById(shellCbId);
                const northCb = document.getElementById(northCbId);
                const southCb = document.getElementById(southCbId);

                function syncDisabledState() {
                    const enabled = shellCb && shellCb.checked;
                    if (northCb) northCb.disabled = !enabled;
                    if (southCb) southCb.disabled = !enabled;
                }

                if (shellCb) {
                    shellCb.addEventListener('change', () => {
                        const vv = ensureShellVisibility(label);
                        vv.showShell = !!shellCb.checked;
                        syncDisabledState();
                        refreshVisibility();
                    });
                }
                if (northCb) {
                    northCb.addEventListener('change', () => {
                        const vv = ensureShellVisibility(label);
                        vv.showNorth = !!northCb.checked;
                        refreshVisibility();
                    });
                }
                if (southCb) {
                    southCb.addEventListener('change', () => {
                        const vv = ensureShellVisibility(label);
                        vv.showSouth = !!southCb.checked;
                        refreshVisibility();
                    });
                }

                syncDisabledState();
            });
        }

        function applyIndependentVisibility() {
            // Global north/south switches removed; per-shell toggles control direction visibility.
            const showNorth = true;
            const showSouth = true;
            const showGroundStations = showGroundStationsEl.checked;
            const showUsers = showUsersEl.checked;
            const showPops = showPopsEl.checked;

            satelliteEntities.forEach((entity) => {
                const shellKey = getShellKeyFromSatellite(entity);
                const v = ensureShellVisibility(shellKey);
                if (!v.showShell) {
                    entity.show = false;
                    return;
                }
                if (entity.directionKey === 'northbound') {
                    entity.show = showNorth && v.showNorth;
                } else if (entity.directionKey === 'southbound') {
                    entity.show = showSouth && v.showSouth;
                } else {
                    entity.show = (showNorth && v.showNorth) || (showSouth && v.showSouth);
                }
            });

            groundStationEntities.forEach((entity) => {
                entity.show = showGroundStations;
            });
            userEntities.forEach((entity) => {
                entity.show = showUsers;
            });
            popEntities.forEach((entity) => {
                entity.show = showPops;
            });
        }

        function refreshVisibility() {
            applyIndependentVisibility();
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
            satelliteEntities.forEach((entity) => {
                const direction = getDirectionAtTime(entity, currentTime);
                entity.directionKey = direction;

                if (direction === 'northbound') {
                    entity.point.outlineColor = Cesium.Color.CYAN;
                    entity.path.material = entity.baseColor.withAlpha(0.55);
                    if (showLabels) {
                        entity.label.text = entity.baseName + ' ↑';
                    }
                } else if (direction === 'southbound') {
                    entity.point.outlineColor = Cesium.Color.MAGENTA;
                    entity.path.material = new Cesium.PolylineDashMaterialProperty({
                        color: entity.baseColor.withAlpha(0.8),
                        dashLength: 12
                    });
                    if (showLabels) {
                        entity.label.text = entity.baseName + ' ↓';
                    }
                } else {
                    entity.point.outlineColor = Cesium.Color.WHITE;
                    entity.path.material = entity.baseColor.withAlpha(0.55);
                    if (showLabels) {
                        entity.label.text = entity.baseName;
                    }
                }

                entity.description = `卫星名称: ${entity.baseName}<br/>壳层: ${entity.shellLabel}<br/>轨道面: ${entity.orbitId}<br/>方向: ${direction}<br/>` +
                    `TLE Line 1: ${entity.tleLine1}<br/>` +
                    `TLE Line 2: ${entity.tleLine2}`;
            });

        }

        showGroundStationsEl.addEventListener('change', refreshVisibility);
        showUsersEl.addEventListener('change', refreshVisibility);
        showPopsEl.addEventListener('change', refreshVisibility);

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
            applyIndependentVisibility();
        });

        setNorthUpTopDownView();

        updateDirectionStylingAndCounts(startTime);
        refreshVisibility();
        renderShellSummary();
        renderShellControls();
        viewer.scene.requestRender();
        statusEl.textContent = `已加载 ${satelliteEntities.length} 颗，失败 ${failedCount} 颗`;
        console.log(`成功加载 ${satelliteEntities.length} 颗卫星，${groundStationEntities.length} 个地面站，${userEntities.length} 个用户点，${popEntities.length} 个POP，失败 ${failedCount} 颗卫星。`);
        })();
    </script>
</body>
</html>
"""


def _infer_shell_id_from_filename(path: Path):
    m = re.search(r"shell[_-]?(\d+)", path.stem, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def read_tle_file(file_path: Path, shell_id: int, shell_label: str):
    satellites = []
    lines = [
        line.strip()
        for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    ]

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
                "shell_id": shell_id,
                "shell_label": shell_label,
            }
        )

    return satellites


def load_satellites_from_tle_files(tle_files):
    satellites = []
    auto_shell_id = 1

    for p in tle_files:
        shell_id = _infer_shell_id_from_filename(p)
        if shell_id is None:
            shell_id = auto_shell_id
            auto_shell_id += 1
        shell_label = f"Shell-{shell_id:03d}"
        satellites.extend(read_tle_file(p, shell_id=shell_id, shell_label=shell_label))

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


def read_users_file(file_path: Path):
    users = []

    def _normalize_header(text: str) -> str:
        return text.strip().lower().replace(" ", "_")

    def _to_float(value):
        return float(str(value).strip())

    with file_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]

    if not rows:
        return users

    first_row = rows[0]
    normalized_headers = [_normalize_header(cell) for cell in first_row]
    lat_candidates = {"lat", "latitude", "latitude_deg", "lat_deg", "纬度"}
    lon_candidates = {"lon", "lng", "longitude", "longitude_deg", "lon_deg", "经度"}
    name_candidates = {"name", "user", "user_name", "city", "id"}
    weight_candidates = {"weight", "count", "population", "users", "demand"}

    header_mode = any(h in lat_candidates or h in lon_candidates for h in normalized_headers)

    lat_idx = lon_idx = name_idx = weight_idx = None
    start_index = 0
    if header_mode:
        start_index = 1
        for idx, header in enumerate(normalized_headers):
            if lat_idx is None and header in lat_candidates:
                lat_idx = idx
            if lon_idx is None and header in lon_candidates:
                lon_idx = idx
            if name_idx is None and header in name_candidates:
                name_idx = idx
            if weight_idx is None and header in weight_candidates:
                weight_idx = idx

    auto_index = 1
    for row in rows[start_index:]:
        try:
            if header_mode and lat_idx is not None and lon_idx is not None:
                latitude_deg = _to_float(row[lat_idx])
                longitude_deg = _to_float(row[lon_idx])
                name = row[name_idx].strip() if name_idx is not None and name_idx < len(row) and row[name_idx].strip() else f"USER-{auto_index:05d}"
                weight = _to_float(row[weight_idx]) if weight_idx is not None and weight_idx < len(row) and row[weight_idx].strip() else 1.0
            else:
                if len(row) >= 4:
                    try:
                        latitude_deg = _to_float(row[2])
                        longitude_deg = _to_float(row[3])
                        name = row[1].strip() if row[1].strip() else f"USER-{auto_index:05d}"
                        weight = _to_float(row[4]) if len(row) > 4 and row[4].strip() else 1.0
                    except ValueError:
                        latitude_deg = _to_float(row[0])
                        longitude_deg = _to_float(row[1])
                        name = row[2].strip() if len(row) > 2 and row[2].strip() else f"USER-{auto_index:05d}"
                        weight = _to_float(row[3]) if len(row) > 3 and row[3].strip() else 1.0
                elif len(row) >= 2:
                    latitude_deg = _to_float(row[0])
                    longitude_deg = _to_float(row[1])
                    name = row[2].strip() if len(row) > 2 and row[2].strip() else f"USER-{auto_index:05d}"
                    weight = _to_float(row[3]) if len(row) > 3 and row[3].strip() else 1.0
                else:
                    continue
        except (ValueError, IndexError):
            continue

        users.append(
            {
                "name": name,
                "latitude_deg": latitude_deg,
                "longitude_deg": longitude_deg,
                "weight": weight,
            }
        )
        auto_index += 1

    return users


def read_pops_file(file_path: Path):
    pops = []

    def _normalize_header(text: str) -> str:
        return text.strip().lower().replace(" ", "_")

    with file_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]

    if not rows:
        return pops

    first_row = rows[0]
    normalized_headers = [_normalize_header(cell) for cell in first_row]
    lat_candidates = {"lat", "latitude", "latitude_deg", "lat_deg", "纬度"}
    lon_candidates = {"lon", "lng", "longitude", "longitude_deg", "lon_deg", "经度"}
    name_candidates = {"pop", "name", "id"}

    header_mode = any(h in lat_candidates or h in lon_candidates for h in normalized_headers)

    lat_idx = lon_idx = name_idx = None
    start_index = 0
    if header_mode:
        start_index = 1
        for idx, header in enumerate(normalized_headers):
            if lat_idx is None and header in lat_candidates:
                lat_idx = idx
            if lon_idx is None and header in lon_candidates:
                lon_idx = idx
            if name_idx is None and header in name_candidates:
                name_idx = idx

    auto_index = 1
    for row in rows[start_index:]:
        try:
            if header_mode and lat_idx is not None and lon_idx is not None:
                latitude_deg = float(str(row[lat_idx]).strip())
                longitude_deg = float(str(row[lon_idx]).strip())
                if name_idx is not None and name_idx < len(row) and row[name_idx].strip():
                    name = row[name_idx].strip()
                else:
                    name = f"POP-{auto_index:05d}"
            else:
                if len(row) >= 3:
                    name = row[0].strip() if row[0].strip() else f"POP-{auto_index:05d}"
                    latitude_deg = float(str(row[1]).strip())
                    longitude_deg = float(str(row[2]).strip())
                elif len(row) >= 2:
                    name = f"POP-{auto_index:05d}"
                    latitude_deg = float(str(row[0]).strip())
                    longitude_deg = float(str(row[1]).strip())
                else:
                    continue
        except (ValueError, IndexError):
            continue

        pops.append(
            {
                "name": name,
                "latitude_deg": latitude_deg,
                "longitude_deg": longitude_deg,
            }
        )
        auto_index += 1

    return pops


def assign_shell_layers(satellites):
    if not satellites:
        return []

    shells = {}
    for sat in satellites:
        sid = sat.get("shell_id")
        label = sat.get("shell_label") or (f"Shell-{int(sid):03d}" if isinstance(sid, int) else "Shell-unknown")
        if sid not in shells:
            shells[sid] = {
                "shell_id": sid if isinstance(sid, int) else 0,
                "label": label,
                "count": 0,
                "avg_altitude_km": None,
                "avg_inclination_deg": None,
            }
        shells[sid]["count"] += 1

    return [shells[k] for k in sorted(shells.keys(), key=lambda x: (isinstance(x, int) is False, x))]


def _cluster_by_raan_pairs(records, threshold_deg: float):
    """Cluster (index, raan_deg) records using the same 1D RAAN heuristic as count_orbits_from_tle.py.

    - Sort by RAAN
    - Group consecutive RAANs if delta <= threshold
    - Merge first/last clusters if they are within threshold across 0/360 wrap
    """
    if not records:
        return []

    sorted_records = sorted(records, key=lambda item: item[1])
    clusters = [[sorted_records[0]]]

    for current in sorted_records[1:]:
        prev = clusters[-1][-1]
        if current[1] - prev[1] <= threshold_deg:
            clusters[-1].append(current)
        else:
            clusters.append([current])

    if len(clusters) > 1 and (sorted_records[0][1] + 360.0 - sorted_records[-1][1]) <= threshold_deg:
        merged = clusters[-1] + clusters[0]
        clusters = [merged] + clusters[1:-1]

    return clusters


def _circular_mean_deg(values):
    if not values:
        return 0.0
    x = sum(math.cos(math.radians(v)) for v in values)
    y = sum(math.sin(math.radians(v)) for v in values)
    ang = math.degrees(math.atan2(y, x))
    return ang % 360.0


def cluster_orbits_by_raan(satellites, raan_threshold_deg: float, orbit_id_base: int = 0):
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

    clusters = _cluster_by_raan_pairs(records, raan_threshold_deg)
    clusters = sorted(clusters, key=lambda c: _circular_mean_deg([item[1] for item in c]))

    # Use 1-based orbit ids to match count_orbits_from_tle.py output indexing.
    # Keep 0 reserved for "unknown" / parse failures.
    for orbit_idx, cluster in enumerate(clusters, start=1):
        for sat_index, _ in cluster:
            satellites[sat_index]["orbit_id"] = orbit_id_base + orbit_idx

    for sat in satellites:
        if "orbit_id" not in sat:
            sat["orbit_id"] = 0

    return len(clusters)


def cluster_orbits_per_shell(satellites, raan_threshold_deg: float):
    shell_to_indices = {}
    for idx, sat in enumerate(satellites):
        sid = sat.get("shell_id")
        shell_to_indices.setdefault(sid, []).append(idx)

    shell_orbit_counts = {}
    for sid, indices in shell_to_indices.items():
        group = [satellites[i] for i in indices]
        base = int(sid) * 1000 if isinstance(sid, int) else 0
        orbit_count = cluster_orbits_by_raan(group, raan_threshold_deg, orbit_id_base=base)
        shell_orbit_counts[sid] = orbit_count
        # Write back orbit_id to original list (group entries are same dict refs)
        # so no extra copy needed.

    return shell_orbit_counts


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


def generate_html(satellites, ground_stations, users, pops, shell_summary, output_path: Path, duration_minutes: int, time_step_seconds: int):
    tle_start_time = get_latest_tle_epoch_utc(satellites)
    tle_start_time_iso = tle_start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    tle_start_time_label = tle_start_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    html_content = (
        HTML_TEMPLATE.replace("__SATELLITES_JSON__", json.dumps(satellites, ensure_ascii=False))
        .replace("__GROUND_STATIONS_JSON__", json.dumps(ground_stations, ensure_ascii=False))
        .replace("__USERS_JSON__", json.dumps(users, ensure_ascii=False))
        .replace("__POPS_JSON__", json.dumps(pops, ensure_ascii=False))
        .replace("__SHELL_SUMMARY_JSON__", json.dumps(shell_summary, ensure_ascii=False))
        .replace("__SAT_COUNT__", str(len(satellites)))
        .replace("__SHELL_COUNT__", str(len(shell_summary)))
        .replace("__GS_COUNT__", str(len(ground_stations)))
        .replace("__USER_COUNT__", str(len(users)))
        .replace("__POP_COUNT__", str(len(pops)))
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
    default_ground_stations_file = str(Path(__file__).resolve().with_name("ground_stations.basic.txt"))
    default_users_file = str(Path(__file__).resolve().with_name("user.txt"))
    default_pops_file = str(Path(__file__).resolve().with_name("pop.txt"))
    parser.add_argument(
        "tle_files",
        nargs="*",
        default=["shell_29.txt"],
        help="输入 TLE 文件路径（可多个，例如 shell_095.tle shell_096.tle shell_129.tle），默认 shell_29.txt",
    )
    parser.add_argument("--output", default="satellites_visualization.html", help="输出 HTML 路径")
    parser.add_argument("--duration-minutes", type=int, default=60, help="轨迹时长（分钟），默认 60")
    parser.add_argument("--time-step-seconds", type=int, default=120, help="轨迹采样步长（秒），默认 120")
    parser.add_argument("--max-satellites", type=int, default=0, help="最多可视化卫星数，0 表示全部")
    parser.add_argument("--raan-threshold", type=float, default=2.0, help="按 RAAN 聚类轨道面的阈值（度），默认 2.0")
    parser.add_argument("--ground-stations", default=default_ground_stations_file, help="地面站文件路径（basic 或 extended，读取前5列），默认 ground_stations.basic.txt")
    parser.add_argument("--users", default=default_users_file, help="用户分布文件路径（CSV，支持 header 或前两列经纬度），默认 user_distribution.txt")
    parser.add_argument("--pops", default=default_pops_file, help="POP 文件路径（CSV，支持表头：pop,latitude,longitude），默认 pop.txt")
    parser.add_argument("--max-users", type=int, default=0, help="最多可视化用户点数量，0 表示全部")
    args = parser.parse_args()

    tle_paths = [Path(p) for p in args.tle_files]
    for p in tle_paths:
        if not p.exists():
            print(f"错误：找不到输入文件 {p}")
            return

    satellites = load_satellites_from_tle_files(tle_paths)
    if not satellites:
        print("错误：未解析到有效 TLE 数据")
        return

    if args.max_satellites > 0:
        satellites = satellites[: args.max_satellites]

    shell_orbit_counts = cluster_orbits_per_shell(satellites, args.raan_threshold)
    shell_summary = assign_shell_layers(satellites)
    # Optionally attach orbit counts without changing UI expectations.
    for item in shell_summary:
        sid = item.get("shell_id")
        item["orbit_count"] = shell_orbit_counts.get(sid)

    ground_stations = []
    if args.ground_stations:
        gs_path = Path(args.ground_stations)
        if not gs_path.exists():
            print(f"错误：找不到地面站文件 {gs_path}")
            return
        ground_stations = read_ground_stations_file(gs_path)

    users = []
    if args.users:
        users_path = Path(args.users)
        if not users_path.exists():
            print(f"错误：找不到用户分布文件 {users_path}")
            return
        users = read_users_file(users_path)
        if args.max_users > 0:
            users = users[: args.max_users]

    pops = []
    if args.pops:
        pops_path = Path(args.pops)
        if not pops_path.exists():
            print(f"错误：找不到 POP 文件 {pops_path}")
            return
        pops = read_pops_file(pops_path)

    output_path = Path(args.output)
    if output_path.parent != Path(""):
        output_path.parent.mkdir(parents=True, exist_ok=True)

    generate_html(satellites, ground_stations, users, pops, shell_summary, output_path, args.duration_minutes, args.time_step_seconds)


if __name__ == "__main__":
    main()
