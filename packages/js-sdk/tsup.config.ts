import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm", "iife"],
  globalName: "DeerFlow",
  dts: true,
  sourcemap: true,
  clean: true,
  external: ["events"],
  splitting: false,
  // 为 IIFE 格式添加 footer 来正确导出
  footer: {
    js: "window.DeerFlow = DeerFlow;"
  }
});
