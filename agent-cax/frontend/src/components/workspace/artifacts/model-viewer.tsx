"use client";

import { useEffect, useRef, useState, useCallback, memo } from "react";

import { cn } from "@/lib/utils";

import ModelToolbar from "./components/ModelToolbar";
import { ModelDrawer, type NctiViewerInstance } from "./ModelDrawer";

export interface ModelViewerPanelProps {
  modelUrl?: string;  // 直接提供模型 URL
  sceneMode?: 0 | 1;  // 场景模式：0=建模，1=草图
  className?: string;
}

const ModelViewerPanel = memo(function ModelViewerPanel({
  modelUrl,
  className
}: ModelViewerPanelProps) {
  const modelViewerRef = useRef<NctiViewerInstance>(null);
  const [modelData, setModelData] = useState<ArrayBuffer | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedUrlRef = useRef<string | null>(null);
  const [sceneMode, setSceneMode] = useState<0 | 1>(0)

  // 加载模型
  const loadModel = useCallback(async (url: string) => {
    setLoading(true);
    setError(null);
    setModelData(undefined);
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`下载失败：${response.status} ${response.statusText}`);
      }
      const data = await response.arrayBuffer();
      setModelData(data);
      loadedUrlRef.current = url;
    } catch (err) {
      console.error("加载模型失败:", err);
      setError(err instanceof Error ? err.message : "加载模型失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // 当 modelUrl 变化时加载模型
  useEffect(() => {
    console.log(modelUrl)
    if (!modelUrl) return;
    // 如果已经加载过这个 URL，跳过
    if (loadedUrlRef.current === modelUrl && modelData) return;
    void loadModel(modelUrl);
  }, [modelUrl, loadModel, modelData]);

  const handleToolbarChange = useCallback((_val: { sceneMode: 0 | 1 }) => {
    // 工具栏控制场景模式切换
    setSceneMode(_val.sceneMode)
  }, []);

  const handleModelMount = useCallback((instance: NctiViewerInstance) => {
    modelViewerRef.current = instance;
  }, []);

  return (
    <div className={cn("flex flex-col size-full", className)}>
      <div className="flex-1 relative bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-800 dark:to-slate-900">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 z-10 bg-background/80 backdrop-blur-sm">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent" />
            <p className="text-muted-foreground text-sm">模型加载中...</p>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 z-10 bg-background/80 backdrop-blur-sm">
            <div className="text-destructive text-4xl">⚠️</div>
            <p className="text-muted-foreground text-sm">{error}</p>
          </div>
        )}
        <div className="flex flex-col h-full">
          <ModelToolbar
            modelViewerRef={modelViewerRef.current}
            onChange={handleToolbarChange}
            sceneMode={sceneMode}
          />
          <ModelDrawer
            onMounted={handleModelMount}
            data={modelData}
            sceneMode={sceneMode}
          />
        </div>
      </div>
    </div>
  );
});

export { ModelViewerPanel };
