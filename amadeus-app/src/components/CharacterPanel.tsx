import React, { useEffect, useRef } from "react"
import * as PIXI from "pixi.js"
import { Live2DSprite } from "easy-live2d"

const CharacterPanel: React.FC = () => {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const appRef = useRef<PIXI.Application | null>(null)

    useEffect(() => {
        const init = async () => {
            if (!canvasRef.current || !containerRef.current) return;

            try {
                // 1. 初始化 Pixi 渲染器 (v8)
                const app = new PIXI.Application();
                appRef.current = app;

                await app.init({
                    canvas: canvasRef.current,
                    backgroundAlpha: 0,
                    width: containerRef.current.clientWidth || 400,
                    height: containerRef.current.clientHeight || 600,
                    preference: 'webgl',
                });
                app.start();

                // 2. 加载 Live2D 模型
                const modelUrl = "/models/Kurisu/steinsGate_kurisu/model0.json";
                const sprite = new Live2DSprite({
                    modelPath: modelUrl,
                    ticker: PIXI.Ticker.shared,
                });
                app.stage.addChild(sprite);

                // 3. 等待模型就绪并调整
                await sprite.ready;

                const canvasW = app.screen.width;
                const canvasH = app.screen.height;
                // modelCanvas是sprite的画布
                const modelCanvas = sprite.getModelCanvasSize();
                if (!modelCanvas) return;
                // 中心对齐
                sprite.pivot.set(modelCanvas.width / 2, modelCanvas.height / 2);
                sprite.x = canvasW / 2;
                sprite.y = canvasH / 2;

                // 适配尺寸，纯凭借经验
                const targetHeight = canvasH * 2;
                sprite.scale.set(targetHeight / sprite.height);

                // 触发开机动作，点亮助手
                sprite.startMotion({
                    group: "phone",
                    no: 0,
                    priority: 3
                });


            } catch (error) {
                console.error("Amadeus 初始化失败:", error);
            }
        };

        const timer = setTimeout(init, 100);

        return () => {
            clearTimeout(timer);
            if (appRef.current) {
                try {
                    appRef.current.destroy(true, { children: true });
                } catch (e) { }
                appRef.current = null;
            }
        };
    }, []);

    return (
        <div ref={containerRef} style={{ flex: 1, width: '100%', height: '100%', position: 'relative' }}>
            <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%' }} />
        </div>
    );
};

export default CharacterPanel;