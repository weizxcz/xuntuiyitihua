"use client";

import { useEffect, useRef, useState, useCallback, memo } from "react";

import { cn } from "@/lib/utils";

import { ShowType } from "./components/ModelToolbar";

// NctiType 枚举
enum NctiType {
  Assembly = 0,
  Part = 1,
}

export interface ModelDrawerProps {
  loading?: boolean;
  updateScene?: boolean;
  data?: ArrayBuffer;
  onMounted?: (instance: NctiViewerInstance) => void;
  onChange?: (type: string) => void;
  selected?: { objectNames: string[]; cellIds: string[] } | null;
  onModelChange?: (type: string) => void;
  className?: string;
  sceneMode: number
  baseDir?: string; // 模型文件所在目录，用于加载装配体零件
}

export interface NctiViewerInstance {
  show: () => void;
  hide: () => void;
  resizeScene: () => void;
  GetSelectedObjectNames: () => string[] | null;
  GetSelectedCellNames: () => string[] | null;
  getScreenShot: () => string | null;
  clearSceneGroup: () => void;
  updateScene: (buffer: ArrayBuffer) => void;
  setShowMode: (mode: number) => void;
  setSelectMode: (mode: number) => void;
  setCellSelect: (objectNames: string[], cellIds: string[]) => void;
  setBodySelect: (bodyName: string, partName: string) => void;
  addNctiBody: (buffer: ArrayBuffer, parentName?: string) => void;
  clearSelected: () => void;
  ZoomAll: () => void;
  SetViewType: (type: number) => void;
  setSelectedVisibleOnly: () => void;
  setAllVisible: () => void;
  setSelectedInvisible: () => void;
  getSceneTree: () => Map<string, string[]>;
  NctiType?: number;
  PartNctiList?: string[];
  SetSceneMode: (mode: number) => void;
}

const ModelDrawer = memo(function ModelDrawer({
  data,
  loading = false,
  updateScene,
  onChange,
  onMounted,
  selected,
  onModelChange,
  className,
  sceneMode,
  baseDir
}: ModelDrawerProps) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const nctiLoaderRef = useRef<NctiViewerInstance | null>(null);
  const updateRef = useRef<boolean | undefined>(updateScene);
  const [assemblyLoading, setAssemblyLoading] = useState(false);

  // 使用 ref 来保持回调函数的稳定引用
  const onChangeRef = useRef(onChange);
  const onMountedRef = useRef(onMounted);
  const onModelChangeRef = useRef(onModelChange);

  useEffect(() => {
    onChangeRef.current = onChange;
    onMountedRef.current = onMounted;
    onModelChangeRef.current = onModelChange;
  }, [onChange, onMounted, onModelChange]);

  // 递归加载装配体的零件
  const loadAssmNcti = useCallback(async (name: string, instance: NctiViewerInstance) => {
    try {
      const url = `${baseDir}/${name}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`下载零件失败：${response.status} ${response.statusText}`);
      }
      const buffer = await response.arrayBuffer();
      instance.addNctiBody(buffer);

      // 如果是装配体，继续递归加载子零件
      if (instance.NctiType === NctiType.Assembly) {
        const partList = instance.PartNctiList ?? [];
        for (const part of partList) {
        await loadAssmNcti(part, instance);
      }
      }
    } catch (error) {
      console.error(`加载零件 ${name} 失败:`, error);
    }
  }, [baseDir]);

  // 加载装配体
  const loadAssembly = useCallback(async (instance: NctiViewerInstance) => {
    if (instance.NctiType === NctiType.Assembly) {
      setAssemblyLoading(true);
      const partList = instance.PartNctiList ?? [];
      for (const part of partList) {
        await loadAssmNcti(part, instance);
      }
      setAssemblyLoading(false);
      onModelChangeRef.current?.("mounted");
    }
  }, [loadAssmNcti]);

  useEffect(() => {
    if (data && canvasRef.current) {
      if (updateRef.current) {
        nctiLoaderRef.current?.updateScene(data);
        onChangeRef.current?.("update");
      } else {
        canvasRef.current.replaceChildren();

        const NctiLoader = window.NctiWebEngine?.NctiLoader;
        if (!NctiLoader) {
          console.error("NctiWebEngine 未加载");
          return;
        }

        const instance = new NctiLoader(data, canvasRef.current, {
          MeshColor: 0xa2afca,
          PointColor: 0xf8cb16,
          SelectedColor: 0xf5800f,
          GridPointColor: 0x00ff00,
        }) as unknown as NctiViewerInstance;
        nctiLoaderRef.current = instance;
        instance.SetSceneMode(sceneMode)
        instance.setShowMode(~ShowType.Point);
        instance.show();
        onMountedRef.current?.(instance);
        onChangeRef.current?.("mounted");

        // 检查是否是装配体，如果是则递归加载零件
        if (instance.NctiType === NctiType.Assembly) {
          void loadAssembly(instance);
        }
        updateRef.current = true;
      }
    }
  }, [data, sceneMode, loadAssembly]);

  useEffect(() => {
    updateRef.current = updateScene;
  }, [updateScene]);

  useEffect(() => {
    if (selected && canvasRef.current && nctiLoaderRef.current) {
      nctiLoaderRef.current.setCellSelect(selected.objectNames, selected.cellIds);
    }
  }, [selected]);

  useEffect(() => {
    if (!canvasRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.target !== canvasRef.current) continue;
        nctiLoaderRef.current?.resizeScene();
        break;
      }
    });
    observer.observe(canvasRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div className={cn("relative flex flex-1 flex-col w-full h-full overflow-hidden", className)}>
      {(loading || assemblyLoading) && (
        <div
          style={{
            position: "absolute",
            zIndex: 99,
            top: 0,
            left: 0,
            right: 0,
            background: "rgba(255,255,255,0.1)",
            height: "100%",
          }}
        >
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-10 w-10 border-4 border-blue-500 border-t-transparent" />
          </div>
        </div>
      )}
      <style>{`
        #container canvas {
          position: absolute;
          top: 0;
          left: 0;
        }
        #container canvas:last-of-type {
          z-index: 9;
          pointer-events: none;
        }
      `}</style>
      <div
        id="container"
        ref={canvasRef}
        style={{
          position: "relative",
          flex: 1,
          width: "100%",
          height: "100%",
          minHeight: "50vh",
          background: sceneMode === 0 ? "linear-gradient(to bottom, #fff, #CED5E1)" : "linear-gradient(to bottom, #05264f, #515a92)",
        }}
      >

      </div>
    </div>
  );
});

export { ModelDrawer };
