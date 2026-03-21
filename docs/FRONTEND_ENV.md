# 前端环境变量配置

前端通过 Vite 环境变量连接后端服务。

## 配置方法

在前端项目根目录（`client/` 或 `frontend/`）下创建 `.env.local` 文件：

```env
# 后端 API 地址（修改此处以连接不同的后端服务器）
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## 变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_API_URL` | `http://localhost:8000` | 后端 REST API 地址 |
| `VITE_WS_URL` | `ws://localhost:8000` | 后端 WebSocket 地址 |

## 示例场景

**本地开发（默认）：**
```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

**局域网其他机器：**
```env
VITE_API_URL=http://192.168.1.100:8000
VITE_WS_URL=ws://192.168.1.100:8000
```

**Docker Compose 部署：**
```env
VITE_API_URL=http://backend:8000
VITE_WS_URL=ws://backend:8000
```

> 修改 `.env.local` 后需要重启前端开发服务器（`pnpm dev`）才能生效。
