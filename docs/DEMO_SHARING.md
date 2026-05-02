# Demo Sharing via Cloudflare Tunnel

让别人通过链接访问你本地运行的 Demo，使用 Cloudflare Tunnel 做内网穿透（免费，支持同时暴露多个端口）。

## 原理

```
访问者浏览器
    ↓ 点击链接（Cloudflare 前端 URL）
Cloudflare 服务器
    ↓ 转发
你的本地 Next.js（port 3000）
    ↓ API 请求
你的本地 FastAPI（port 8001）← 也通过 Cloudflare 暴露
```

因为前端调用的 API 地址是由 `NEXT_PUBLIC_API_URL` 决定的，必须把前后端都暴露出去，否则访问者的浏览器会去请求他们自己的 `localhost:8001`（不是你的机器）。

---

## 步骤

### 1. 安装 cloudflared

```bash
brew install cloudflare/cloudflare/cloudflared
```

不需要注册账号，不需要 token，免费直接用。

---

### 2. 启动后端

确认 FastAPI 已在 8001 端口运行：

```bash
cd /path/to/Flex-Practicum-Project-2026
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

---

### 3. 新开终端，暴露后端，记录 URL

```bash
cloudflared tunnel --url http://localhost:8001
```

等待约 10 秒，终端会显示：

```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://xxxx-xxxx-xxxx.trycloudflare.com                                                  |
+--------------------------------------------------------------------------------------------+
```

**复制这个 `https://xxxx-xxxx-xxxx.trycloudflare.com`，下一步要用。**

---

### 4. 关掉当前前端，用后端 URL 重新启动

先 Ctrl+C 停掉正在跑的 `npm run dev`，然后：

```bash
cd /path/to/Flex-Practicum-Project-2026/frontend
NEXT_PUBLIC_API_URL=https://xxxx-xxxx-xxxx.trycloudflare.com npm run dev
```

把地址替换成第 3 步拿到的后端 Cloudflare URL。

---

### 5. 新开终端，暴露前端，获取分享链接

```bash
cloudflared tunnel --url http://localhost:3000
```

终端会显示：

```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://yyyy-yyyy-yyyy.trycloudflare.com                                                  |
+--------------------------------------------------------------------------------------------+
```

**把这个 `https://yyyy-yyyy-yyyy.trycloudflare.com` 分享给别人。**

---

## 注意事项

| 事项 | 说明 |
|------|------|
| 无需账号 | Cloudflare 免费 Quick Tunnel 不需要注册 |
| URL 每次随机 | 每次重启 cloudflared 都会生成新的地址 |
| 本机必须保持运行 | 关闭任意一个终端（后端/前端/cloudflared）链接即失效 |
| 访问者首次打开 | 可能看到 Cloudflare 警告页，点击继续即可 |
| ChromaDB 数据 | 数据在你本地，访问者看到的是你本地数据库的内容 |

---

## 完整终端分工总览

| 终端 | 命令 | 作用 |
|------|------|------|
| 终端 1 | `uvicorn backend.main:app --port 8001` | 跑后端 |
| 终端 2 | `cloudflared tunnel --url http://localhost:8001` | 暴露后端，记录 URL |
| 终端 3 | `NEXT_PUBLIC_API_URL=<后端URL> npm run dev` | 跑前端（带后端地址） |
| 终端 4 | `cloudflared tunnel --url http://localhost:3000` | 暴露前端，获取分享链接 |

---

## 每次启动快速命令（第二次起照着跑）

> URL 每次随机变，步骤顺序不变。

**终端 1 — 后端**
```bash
cd ~/Desktop/courses/quarter_2/pra_before/practicum_demo/Flex-Practicum-Project-2026
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

**终端 2 — 暴露后端（记录输出的 URL）**
```bash
cloudflared tunnel --url http://localhost:8001
```

**终端 3 — 前端（把上面的 URL 填进去）**
```bash
cd ~/Desktop/courses/quarter_2/pra_before/practicum_demo/Flex-Practicum-Project-2026/frontend
NEXT_PUBLIC_API_URL=https://在这里粘贴终端2的URL.trycloudflare.com npm run dev
```

**终端 4 — 暴露前端（输出的 URL 就是分享链接）**
```bash
cloudflared tunnel --url http://localhost:3000
```
