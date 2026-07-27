"use client";

import { useCallback, useState } from "react";

import { cn } from "@/lib/utils";

import type { NctiViewerInstance } from "../ModelDrawer";

// 场景模式枚举
export enum SceneMode {
  ThreeD = 1,
  Sketch = 0,
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

export interface ModelToolbarProps {
  modelViewerRef: React.RefObject<NctiViewerInstance | null>;
  onChange?: (value: { sceneMode: SceneMode }) => void;
  className?: string;
}

export default function ModelToolbar({ modelViewerRef, onChange, className }: ModelToolbarProps) {
  const [bodyActive, setBodyActive] = useState(true);
  const [meshActive, setMeshActive] = useState(true);
  const [lineActive, setLineActive] = useState(true);
  const [pointActive, setPointActive] = useState(true);
  const [sceneMode, setSceneMode] = useState<SceneMode>(SceneMode.Sketch);
  const [showValues, setShowValues] = useState<string[]>(["body", "mesh", "line", "point"]);

  const handleSceneModeChange = useCallback(() => {
    const newMode = sceneMode === SceneMode.ThreeD ? SceneMode.Sketch : SceneMode.ThreeD;
    setSceneMode(newMode);
    console.log(newMode);
    (modelViewerRef.current as any)?.SetSceneMode?.(newMode);
    onChange?.({ sceneMode: newMode });
  }, [sceneMode, modelViewerRef, onChange]);

  const handleBodySelect = useCallback(() => {
    const newBodyActive = !bodyActive;
    setBodyActive(newBodyActive);

    if (newBodyActive) {
      modelViewerRef.current?.setSelectMode?.(
        SelectType.Body | SelectType.Face | SelectType.Edge | SelectType.Point
      );
      setMeshActive(true);
      setLineActive(true);
      setPointActive(true);
    } else {
      modelViewerRef.current?.setSelectMode?.(SelectType.None | SelectType.Face | SelectType.Edge | SelectType.Point);
    }
  }, [bodyActive, modelViewerRef]);

  const handleMeshSelect = useCallback(() => {
    const newMeshActive = !meshActive;
    setMeshActive(newMeshActive);
    if (!newMeshActive) {
      setBodyActive(false);
    }
    modelViewerRef.current?.setSelectMode?.(
      SelectType.None |
        (newMeshActive ? SelectType.Face : SelectType.None) |
        (lineActive ? SelectType.Edge : SelectType.None) |
        (pointActive ? SelectType.Point : SelectType.None)
    );
  }, [meshActive, lineActive, pointActive, modelViewerRef]);

  const handleLineSelect = useCallback(() => {
    const newLineActive = !lineActive;
    setLineActive(newLineActive);
    if (!newLineActive) {
      setBodyActive(false);
    }
    modelViewerRef.current?.setSelectMode?.(
      SelectType.None |
        (meshActive ? SelectType.Face : SelectType.None) |
        (newLineActive ? SelectType.Edge : SelectType.None) |
        (pointActive ? SelectType.Point : SelectType.None)
    );
  }, [lineActive, meshActive, pointActive, modelViewerRef]);

  const handlePointSelect = useCallback(() => {
    const newPointActive = !pointActive;
    setPointActive(newPointActive);
    if (!newPointActive) {
      setBodyActive(false);
    }
    modelViewerRef.current?.setSelectMode?.(
      SelectType.None |
        (meshActive ? SelectType.Face : SelectType.None) |
        (lineActive ? SelectType.Edge : SelectType.None) |
        (newPointActive ? SelectType.Point : SelectType.None)
    );
  }, [pointActive, meshActive, lineActive, modelViewerRef]);

  const handleCheckboxChange = useCallback(
    (checkedValue: string[]) => {
      let newValue: string[];

      const isAddingBody = checkedValue.includes("body") && !showValues.includes("body");
      const isRemovingBody = !checkedValue.includes("body") && showValues.includes("body");
      const isChangingMeshLinePoint =
        checkedValue.includes("mesh") !== showValues.includes("mesh") ||
        checkedValue.includes("line") !== showValues.includes("line") ||
        checkedValue.includes("point") !== showValues.includes("point");

      if (isAddingBody) {
        newValue = ["body", "mesh", "line", "point"];
        modelViewerRef.current?.setShowMode(ShowType.Body);
      } else if (isRemovingBody) {
        newValue = checkedValue.filter((v) => v !== "body");
        const showMode =
          (newValue.includes("mesh") ? ShowType.Face : ShowType.None) |
          (newValue.includes("line") ? ShowType.Edge : ShowType.None) |
          (newValue.includes("point") ? ShowType.Point : ShowType.None);
        modelViewerRef.current?.setShowMode(showMode);
      } else if (isChangingMeshLinePoint) {
        const hasMesh = checkedValue.includes("mesh");
        const hasLine = checkedValue.includes("line");
        const hasPoint = checkedValue.includes("point");

        if (hasMesh && hasLine && hasPoint) {
          newValue = ["body", "mesh", "line", "point"];
        } else {
          newValue = checkedValue.filter((v) => v !== "body");
        }

        const showMode =
          (newValue.includes("mesh") ? ShowType.Face : ShowType.None) |
          (newValue.includes("line") ? ShowType.Edge : ShowType.None) |
          (newValue.includes("point") ? ShowType.Point : ShowType.None);
        modelViewerRef.current?.setShowMode(showMode);
      } else {
        newValue = checkedValue;
        const showMode =
          (newValue.includes("mesh") ? ShowType.Face : ShowType.None) |
          (newValue.includes("line") ? ShowType.Edge : ShowType.None) |
          (newValue.includes("point") ? ShowType.Point : ShowType.None);
        modelViewerRef.current?.setShowMode(showMode);
      }

      setShowValues(newValue);
    },
    [showValues, modelViewerRef]
  );

  const handleViewChange = useCallback(
    (operation: "add" | "minus", direction: "X" | "Y" | "Z") => {
      const opMap = {
        add: ViewType[`Negative${direction}`] as number,
        minus: ViewType[`Positive${direction}`] as number,
      };
      modelViewerRef.current?.SetViewType(opMap[operation]);
    },
    [modelViewerRef]
  );

  const handleZoomAll = useCallback(() => {
    modelViewerRef.current?.ZoomAll();
  }, [modelViewerRef]);

  const handleShowAll = useCallback(() => {
    modelViewerRef.current?.setAllVisible();
  }, [modelViewerRef]);

  const handleHideAll = useCallback(() => {
    modelViewerRef.current?.setSelectedInvisible();
  }, [modelViewerRef]);

  const handleViewOnly = useCallback(() => {
    modelViewerRef.current?.setSelectedVisibleOnly();
  }, [modelViewerRef]);

  return (
    <div className={cn("flex items-center gap-1 px-2 py-1 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 w-full", className)} style={{ overflowX: 'auto' }}>
      {/* 选择模式 */}
      <div onClick={handleBodySelect} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors">
        <div className={cn("w-7 h-7 flex items-center justify-center", bodyActive ? "text-blue-500" : "text-slate-400")}>
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="2" fill="none" />
            <rect x="7" y="7" width="10" height="10" fill="currentColor" />
          </svg>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">体</span>
      </div>

      <div onClick={handleMeshSelect} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors">
        <div className={cn("w-7 h-7 flex items-center justify-center", meshActive ? "text-blue-500" : "text-slate-400")}>
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <path d="M3 3L12 7L21 3V11L12 15L3 11V3Z" stroke="currentColor" strokeWidth="2" fill="none" />
            <path d="M3 11L12 15V21L3 17V11Z" stroke="currentColor" strokeWidth="2" fill="none" />
            <path d="M12 15L21 11V17L12 21V15Z" stroke="currentColor" strokeWidth="2" fill="none" />
          </svg>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">面</span>
      </div>

      <div onClick={handleLineSelect} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors">
        <div className={cn("w-7 h-7 flex items-center justify-center", lineActive ? "text-blue-500" : "text-slate-400")}>
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <path d="M3 3L21 21" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            <path d="M3 21L21 3" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          </svg>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">线</span>
      </div>

      <div onClick={handlePointSelect} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors">
        <div className={cn("w-7 h-7 flex items-center justify-center", pointActive ? "text-blue-500" : "text-slate-400")}>
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" fill="none" />
            <circle cx="12" cy="12" r="3" fill="currentColor" />
          </svg>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">点</span>
      </div>

      <div className="w-px h-8 bg-slate-300 dark:bg-slate-600 mx-1" />

      {/* 显示控制 */}
      <div onClick={handleShowAll} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors" title="显示全部">
        <div className="w-7 h-7 flex items-center justify-center text-slate-400">
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <path d="M4 4H10V10H4V4ZM14 4H20V10H14V4ZM4 14H10V20H4V14ZM14 14H20V20H14V14Z" fill="currentColor" />
          </svg>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">显示</span>
      </div>

      <div onClick={handleHideAll} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors" title="隐藏全部">
        <div className="w-7 h-7 flex items-center justify-center text-slate-400">
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <path d="M4 4H10V6H6V10H4V4ZM14 4H20V10H18V6H14V4ZM4 14H6V18H10V20H4V14ZM14 14H20V20H14V14Z" fill="currentColor" />
          </svg>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">隐藏</span>
      </div>

      <div onClick={handleViewOnly} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors" title="独显">
        <div className="w-7 h-7 flex items-center justify-center text-slate-400">
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <rect x="6" y="6" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="2" fill="none" />
          </svg>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">独显</span>
      </div>

      <div className="w-px h-8 bg-slate-300 dark:bg-slate-600 mx-1" />

      {/* 显示模式复选框 */}
      <div className="flex flex-wrap items-center gap-1 bg-slate-100 dark:bg-slate-700 rounded px-2 py-1 w-[80px]">
        {["body", "mesh", "line", "point"].map((item) => (
          <label key={item} className="flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={showValues.includes(item)}
              onChange={(e) => {
                const newValue = e.target.checked
                  ? [...showValues, item]
                  : showValues.filter((v) => v !== item);
                handleCheckboxChange(newValue);
              }}
              className="w-3 h-3 rounded border-slate-300 text-blue-500 focus:ring-blue-500"
            />
            <span className="text-xs text-slate-600 dark:text-slate-300">
              {item === "body" ? "体" : item === "mesh" ? "面" : item === "line" ? "线" : "点"}
            </span>
          </label>
        ))}
      </div>

      <div className="w-px h-8 bg-slate-300 dark:bg-slate-600 mx-1" />

      {/* 视图方向 */}
      <div className="flex flex-col gap-1">
        <div className="flex gap-1">
          <button
            onClick={() => handleViewChange("add", "X")}
            className="w-8 h-6 flex items-center justify-center rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs text-slate-600 dark:text-slate-300"
          >
            X+
          </button>
          <button
            onClick={() => handleViewChange("add", "Y")}
            className="w-8 h-6 flex items-center justify-center rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs text-slate-600 dark:text-slate-300"
          >
            Y+
          </button>
          <button
            onClick={() => handleViewChange("add", "Z")}
            className="w-8 h-6 flex items-center justify-center rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs text-slate-600 dark:text-slate-300"
          >
            Z+
          </button>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => handleViewChange("minus", "X")}
            className="w-8 h-6 flex items-center justify-center rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs text-slate-600 dark:text-slate-300"
          >
            X-
          </button>
          <button
            onClick={() => handleViewChange("minus", "Y")}
            className="w-8 h-6 flex items-center justify-center rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs text-slate-600 dark:text-slate-300"
          >
            Y-
          </button>
          <button
            onClick={() => handleViewChange("minus", "Z")}
            className="w-8 h-6 flex items-center justify-center rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs text-slate-600 dark:text-slate-300"
          >
            Z-
          </button>
        </div>
      </div>

      <div className="w-px h-8 bg-slate-300 dark:bg-slate-600 mx-1" />

      {/* 场景模式切换 */}
      <div onClick={handleSceneModeChange} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors" title={sceneMode === SceneMode.ThreeD ? "切换到草图模式" : "切换到 3D 模型模式"}>
        <div className="w-7 h-7 flex items-center justify-center">
          {sceneMode === SceneMode.ThreeD ? (
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6 text-blue-500">
              <rect x="3" y="3" width="7" height="7" rx="1" fill="currentColor" />
              <rect x="14" y="3" width="7" height="7" rx="1" fill="currentColor" />
              <rect x="3" y="14" width="7" height="7" rx="1" fill="currentColor" />
              <rect x="14" y="14" width="7" height="7" rx="1" fill="currentColor" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6 text-green-500">
              <path d="M3 12L12 3L21 12L12 21L3 12Z" stroke="currentColor" strokeWidth="2" fill="none" />
              <path d="M12 3V21" stroke="currentColor" strokeWidth="2" />
              <path d="M3 12H21" stroke="currentColor" strokeWidth="2" />
            </svg>
          )}
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">{sceneMode === SceneMode.ThreeD ? "模型" : "草图"}</span>
      </div>

      <div className="w-px h-8 bg-slate-300 dark:bg-slate-600 mx-1" />

      {/* 缩放控制 */}
      <div onClick={handleZoomAll} className="flex flex-col items-center justify-center p-1 px-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors" title="缩放">
        <div className="w-7 h-7 flex items-center justify-center text-slate-400">
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <path d="M15 3L21 3L21 9" stroke="currentColor" strokeWidth="2" fill="none" />
            <path d="M9 21L3 21L3 15" stroke="currentColor" strokeWidth="2" fill="none" />
            <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="2" fill="none" />
            <path d="M12 9V15M9 12H15" stroke="currentColor" strokeWidth="2" />
          </svg>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 mt-1">缩放</span>
      </div>
    </div>
  );
}
