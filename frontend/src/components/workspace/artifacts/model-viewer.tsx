"use client";

import { useEffect, useRef, useState, useCallback } from "react";

import { urlOfArtifact } from "@/core/artifacts/utils";
import { cn } from "@/lib/utils";

import ModelToolbar from "./components/ModelToolbar";
import { ModelDrawer } from "./ModelDrawer";

// NCTI Web Engine 类型定义
declare global {
  interface Window {
    NctiWebEngine?: {
      NctiLoader: new (
        data: ArrayBuffer,
        container: HTMLElement,
        config?: {
          MeshColor?: number;
          PointColor?: number;
          SelectedColor?: number;
          GridPointColor?: number;
        },
      ) => NctiViewerInstance;
    };
  }
}

interface NctiViewerInstance {
  show: () => void;
  hide: () => void;
  resizeScene: () => void;
  GetSelectedObjectNames: () => string[] | null;
  GetSelectedCellNames: () => string[] | null;
  getScreenShot: () => string | null;
  clearSceneGroup: () => void;
  setShowMode: (mode: number) => void;
  setSelectMode: (mode: number) => void;
  setBodySelect: (bodyName: string, partName: string) => void;
  setCellSelect: (objectNames: string[], cellIds: string[]) => void;
  clearSelected: () => void;
  ZoomAll: () => void;
  SetViewType: (type: number) => void;
  setSelectedVisibleOnly: () => void;
  setAllVisible: () => void;
  setSelectedInvisible: () => void;
  getSceneTree: () => Map<string, string[]>;
  updateScene: (buffer: ArrayBuffer) => void;
  addNctiBody: (buffer: ArrayBuffer, parentName?: string) => void;
  NctiType?: number;
  PartNctiList?: string[];
}

// 显示模式枚举
export enum ShowType {
  None = 0,
  Body = 1,
  Face = 2,
  Edge = 4,
  Point = 8,
}

// 选择模式枚举
export enum SelectType {
  None = 0,
  Body = 1,
  Face = 2,
  Edge = 4,
  Point = 8,
}

// 视图类型枚举
export enum ViewType {
  PositiveX = 1,
  NegativeX = 2,
  PositiveY = 3,
  NegativeY = 4,
  PositiveZ = 5,
  NegativeZ = 6,
}


// 带加载状态的模型查看器面板
export interface ModelViewerPanelProps {
  filepath: string;
  threadId: string;
  className?: string;
}

export function ModelViewerPanel({ filepath, threadId, className }: ModelViewerPanelProps) {
  const modelViewerRef = useRef<NctiViewerInstance>(null);
  const [modelData, setModelData] = useState<ArrayBuffer | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sceneMode, setSceneMode] = useState<0 | 1>(0)

  // 加载模型文件 URL
  const modelUrl = urlOfArtifact({ filepath, threadId });

  // 加载模型
  const loadModel = useCallback(async (url: string) => {
    setLoading(true);
    setError(null);
    setModelData(undefined);
    try {
      // 添加时间戳参数绕过浏览器缓存
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`下载失败：${response.status} ${response.statusText}`);
      }
      const data = await response.arrayBuffer();
      setModelData(data);
      setLoading(false);
    } catch (err) {
      console.error("加载模型失败:", err);
      setError(err instanceof Error ? err.message : "加载模型失败");
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!modelUrl) return;
    void loadModel(modelUrl);
  }, [modelUrl, filepath, loadModel]);

  return (
    <div className={cn("flex flex-col size-full", className)}>
      {/* 模型查看区域 */}
      <div className="flex-1 relative bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-800 dark:to-slate-900">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 z-10 bg-background/80 backdrop-blur-sm">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent" />
            <p className="text-muted-foreground text-sm">模型加载中...</p>
          </div>
        )}

        {error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 z-10 bg-background/80 backdrop-blur-sm">
            <div className="text-destructive text-4xl">⚠️</div>
            <p className="text-muted-foreground text-sm">{error}</p>
          </div>
        )}
        <div className="flex flex-col h-full">
          <ModelToolbar modelViewerRef={modelViewerRef} onChange={(val) => {
            setSceneMode(val.sceneMode)
          }}/>
          <ModelDrawer
            onMounted={instance => modelViewerRef.current = instance}
            data={modelData}
            sceneMode={sceneMode}
          />
        </div>
      </div>
    </div>
  );
}
