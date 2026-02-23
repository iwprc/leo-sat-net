#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能：读取 TLE 文件，生成 Cesium 卫星轨道可视化 HTML。
依赖：需要安装 Jinja2 库 (pip install Jinja2)
输入：同级目录下的 tle.txt 文件
输出：satellites_visualization.html
"""

import json
from jinja2 import Template

def read_tle_file(file_path):
    """
    读取 TLE 文件，解析为卫星对象列表。
    格式假设：每颗卫星由三行组成（名称行，TLE行1，TLE行2）。
    """
    satellites = []
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.rstrip('\n') for line in f]

    i = 1
    while i < len(lines):

        # 第一行：卫星名称
        name_line = lines[i].strip()
        # 文档中第一行似乎是"序号"和"名称"，我们取后半部分作为名称
        sat_name = name_line.replace(' ', '-')

        i += 1
        if i >= len(lines):
            break
        tle_line1 = lines[i].strip()

        i += 1
        if i >= len(lines):
            break
        tle_line2 = lines[i].strip()

        # 存储这颗卫星的信息
        satellites.append({
            "name": sat_name,
            "tle_line1": tle_line1,
            "tle_line2": tle_line2
        })
        i += 1

    return satellites

def generate_html(satellites, output_path="satellites_visualization.html"):
    """
    使用 Jinja2 模板生成最终的 HTML 文件。
    """
    # HTML 模板 (内嵌 JavaScript)
    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cesium TLE Satellite Visualization</title>
    <!-- 使用稳定的 Cesium 版本 -->
    <script src="https://cesium.com/downloads/cesiumjs/releases/1.107/Build/Cesium/Cesium.js"></script>
    <link rel="stylesheet" href="https://cesium.com/downloads/cesiumjs/releases/1.107/Build/Cesium/Widgets/widgets.css">
    <!-- 引入 satellite.js 用于 TLE 解析和 SGP4 计算 -->
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
            background-color: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 12px;
            z-index: 1000;
            max-width: 300px;
        }
        #debugPanel {
            position: absolute;
            top: 10px;
            right: 10px;
            background-color: rgba(0, 0, 0, 0.7);
            color: #0f0;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 12px;
            z-index: 1000;
            max-width: 300px;
        }
    </style>
</head>
<body>
    <div id="cesiumContainer"></div>
    <div id="infoPanel">
        <div>卫星数量：{{ sat_count }}</div>
        <div>时间：<span id="currentTime"></span></div>
        <div>点击卫星查看详情</div>
    </div>
    <div id="debugPanel">
        <div>状态：<span id="status">初始化中...</span></div>
    </div>

    <script>
        // 配置 Cesium 基础 URL
        Cesium.buildModuleUrl.setBaseUrl('https://cesium.com/downloads/cesiumjs/releases/1.107/Build/Cesium/');

        // 创建 Viewer，使用最简配置
        const viewer = new Cesium.Viewer('cesiumContainer', {
            timeline: true,
            animation: true,
            baseLayerPicker: false,
            geocoder: false,
            homeButton: true,
            sceneModePicker: true,
            navigationHelpButton: false,
            fullscreenButton: true,
            // 使用椭球地形
            terrainProvider: new Cesium.EllipsoidTerrainProvider(),
            // 不设置影像提供者
            imageryProvider: false
        });

        // 获取地球对象
        const globe = viewer.scene.globe;

        // 1. 确保地球可见
        globe.show = true;

        globe.baseColor = Cesium.Color.LIGHTBLUE; // 浅蓝

        // 3. 移除所有影像层
        globe.imageryLayers.removeAll();

        // 4. 创建纯色影像层
        const solidColorLayer = globe.imageryLayers.addImageryProvider(
            new Cesium.SingleTileImageryProvider({
                url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
                rectangle: Cesium.Rectangle.MAX_VALUE
            })
        );

        // 5. 禁用不必要效果
        globe.enableLighting = false;
        globe.depthTestAgainstTerrain = true;
        globe.translucency.enabled = false;
        viewer.scene.fog.enabled = false;
        viewer.scene.skyAtmosphere.show = false;
        viewer.scene.skyBox.show = false;

        // 6. 设置不透明度
        globe.opacity = 1.0;

        // 7. 设置背景色
        viewer.scene.backgroundColor = Cesium.Color.BLACK;

        // 8. 隐藏版权信息
        viewer._cesiumWidget._creditContainer.style.display = "none";

        // 更新状态
        document.getElementById('status').textContent = 'Cesium 初始化完成';

        // 2. 定义卫星数据（从 Python 传入）
        const rawSatellites = {{ satellites_json | safe }};

        // 3. 将卫星 TLE 数据解析为 satellite.js 可用的格式，并创建 Cesium 实体
        const satelliteEntities = [];
        const colors = [
            Cesium.Color.RED,
            Cesium.Color.GREEN,
            Cesium.Color.BLUE,
            Cesium.Color.YELLOW,
            Cesium.Color.PURPLE,
            Cesium.Color.CYAN,
            Cesium.Color.ORANGE,
            Cesium.Color.PINK,
            Cesium.Color.LIME,
            Cesium.Color.AQUA
        ];

        // 定义时间范围变量
        const startTime = Cesium.JulianDate.now();
        const stopTime = Cesium.JulianDate.addSeconds(startTime, 90 * 60, new Cesium.JulianDate());

        rawSatellites.forEach((sat, index) => {
            try {
                // 解析 TLE
                const satrec = satellite.twoline2satrec(sat.tle_line1, sat.tle_line2);

                // 为每颗卫星创建一个 SampledPositionProperty 来存储一段时间内的位置
                const positionProperty = new Cesium.SampledPositionProperty();

                // 计算从现在开始未来 90 分钟的轨迹
                const timeStepInSeconds = 60;

                let currentTime = Cesium.JulianDate.clone(startTime);
                while (Cesium.JulianDate.compare(currentTime, stopTime) <= 0) {
                    const jsDate = Cesium.JulianDate.toDate(currentTime);
                    const positionAndVelocity = satellite.propagate(satrec, jsDate);
                    
                    if (positionAndVelocity.position) {
                        const gmst = satellite.gstime(jsDate);
                        const positionEcf = satellite.eciToEcf(positionAndVelocity.position, gmst);

                        const position = new Cesium.Cartesian3(
                            positionEcf.x * 1000,
                            positionEcf.y * 1000,
                            positionEcf.z * 1000
                        );

                        positionProperty.addSample(currentTime, position);
                    }

                    currentTime = Cesium.JulianDate.addSeconds(currentTime, timeStepInSeconds, new Cesium.JulianDate());
                }

                const color = colors[index % colors.length];

                // 创建 Cesium 实体
                const entity = viewer.entities.add({
                    name: sat.name,
                    position: positionProperty,
                    orientation: new Cesium.VelocityOrientationProperty(positionProperty),
                    point: {
                        pixelSize: 12,
                        color: color,
                        outlineColor: Cesium.Color.WHITE,
                        outlineWidth: 2,
                        heightReference: Cesium.HeightReference.NONE,
                    },
                    label: {
                        text: sat.name,
                        font: '14px sans-serif',
                        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                        outlineWidth: 2,
                        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                        pixelOffset: new Cesium.Cartesian2(0, -20),
                        showBackground: true,
                        backgroundColor: new Cesium.Color(0.1, 0.1, 0.1, 0.7),
                        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 10000000)
                    },
                    description: `卫星名称: ${sat.name}<br/>TLE Line 1: ${sat.tle_line1}<br/>TLE Line 2: ${sat.tle_line2}`
                });

                satelliteEntities.push(entity);
            } catch (error) {
                console.error(`解析卫星 ${sat.name} 的 TLE 数据时出错:`, error);
            }
        });

        // 4. 设置时钟范围
        viewer.clock.startTime = startTime.clone();
        viewer.clock.stopTime = stopTime.clone();
        viewer.clock.currentTime = startTime.clone();
        viewer.clock.multiplier = 60;
        viewer.clock.clockRange = Cesium.ClockRange.LOOP_STOP;
        viewer.timeline.zoomTo(startTime, stopTime);

        // 5. 更新信息面板
        viewer.clock.onTick.addEventListener(function() {
            const currentTime = Cesium.JulianDate.toDate(viewer.clock.currentTime);
            document.getElementById('currentTime').textContent = currentTime.toUTCString();
        });

        // 6. 设置相机视角
        viewer.camera.setView({
            destination: Cesium.Cartesian3.fromDegrees(0, 0, 25000000),
            orientation: {
                heading: 0,
                pitch: -Math.PI/2,
                roll: 0
            }
        });
        // 确保地球完全不透明
        viewer.scene.globe.translucency.enabled = false; // 完全禁用半透明渲染
        viewer.scene.globe.opacity = 1.0; // 设置全局不透明度为100%

        // 添加以下代码，在地球配置完成后，强制场景立即渲染
        setTimeout(() => {
            viewer.scene.requestRender();
            console.log('强制渲染场景。当前地球颜色:', viewer.scene.globe.baseColor);
        }, 500); // 延迟500毫秒执行，确保配置已生效

        console.log(`成功加载 ${satelliteEntities.length} 颗卫星。`);
        console.log('地球配置:', {
            show: globe.show,
            baseColor: globe.baseColor,
            enableLighting: globe.enableLighting,
            depthTestAgainstTerrain: globe.depthTestAgainstTerrain
        });
        
        // 强制渲染一帧
        viewer.scene.requestRender();
        
    </script>
</body>
</html>
    """

    # 准备模板数据
    template_data = {
        "satellites_json": json.dumps(satellites, ensure_ascii=False),
        "sat_count": len(satellites)
    }

    # 渲染模板
    template = Template(html_template)
    html_content = template.render(**template_data)

    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"生成成功！文件已保存为: {output_path}")
    print(f"共处理了 {len(satellites)} 颗卫星。")
    print(f"请用浏览器打开 {output_path} 文件查看可视化效果。")

def main():
    # 读取 TLE 文件（假设文件名为 tle.txt，与脚本在同一目录）
    tle_file = "tle.txt"
    try:
        satellites = read_tle_file(tle_file)
        if not satellites:
            print("错误：未从文件中解析到任何有效的 TLE 数据。")
            return
    except FileNotFoundError:
        print(f"错误：找不到文件 {tle_file}。请确保它位于当前目录。")
        return

    # 生成 HTML 文件
    generate_html(satellites)

if __name__ == "__main__":
    main()