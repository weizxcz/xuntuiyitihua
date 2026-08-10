# NTIC-CAX-Agent 项目记忆

## 项目性质
- DeerFlow（LangGraph AI Agent）派生项目，CAX 工程研发 Agent 平台，接入 NCTI 草图内核。
- 三件套：Gateway(后端 :8001) + Frontend(Next.js :3000) + Nginx(反向代理 :2026)，统一入口 http://localhost:2026。

## 启动方式（Windows 环境，已验证可行）
- 纯 Windows（非 WSL）可直接跑，绕开 nginx：分别后台启动 backend(uv run uvicorn :8001) + frontend(npm run dev :3000)，访问 http://localhost:3000。
- 后端：`cmd /c "set PYTHONUNBUFFERED=1 && C:\Users\admin\.local\bin\uv.exe run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --reload > gateway.log 2>&1"`（WorkingDirectory=backend）。
- 前端：`cmd /c "npm run dev > frontend.log 2>&1"`（WorkingDirectory=frontend；pnpm 因 Node 22.12.0<22.13 报错，用 npm）。
- 停服：`Get-Process | ?{$_.Name -match "uvicorn|^uv$|next"} | Stop-Process -Force`。
- make dev / WSL2 / Docker 也支持，但本机已验证纯 Windows 方案可用，优先用此。
- 详细坑见 2026-07-21 daily。

## 已就绪配置
- config.yaml 已存在：默认 sqlite、sandbox=LocalSandboxProvider（本地沙箱，无需拉 AIO 沙箱镜像）、allow_host_bash=true。
- .env 已配 Agent 指向内网 Qwen endpoint：AGENT_BASE_URL=http://172.16.55.7:9025/v1，AGENT_MODEL=Qwen3.5-122B-A10B，AGENT_API_KEY=empty。

## 用户偏好
- 实习生身份；要"直接可复制的命令"，少背景铺垫。
- 写实习产出/简历用 STAR 法则、量化指标（详见 2026-07-20 daily）。
