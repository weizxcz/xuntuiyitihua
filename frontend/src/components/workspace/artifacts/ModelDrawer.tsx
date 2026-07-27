"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

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

export function ModelDrawer({
  data,
  loading = false,
  updateScene,
  onChange,
  onMounted,
  selected,
  onModelChange,
  className,
  sceneMode
}: ModelDrawerProps) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const nctiLoaderRef = useRef<NctiViewerInstance | null>(null);
  const updateRef = useRef<boolean | undefined>(updateScene);

  useEffect(() => {
    if (data && canvasRef.current) {
      if (updateRef.current) {
        nctiLoaderRef.current?.updateScene(data);
        onChange?.("update");
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
        instance.setShowMode(0);
        instance.show();
        onMounted?.(instance);
        onChange?.("mounted");

        // 检查是否是装配体
        if (instance.NctiType === 0) { // NctiType.Assembly = 0
          onModelChange?.("mounted");
        }
        updateRef.current = true;
      }
    }
  }, [data]);

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
      {loading && (
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
}
