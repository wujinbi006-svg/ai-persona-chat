# AI 人格聊天平台

一个极简的 AI 人格聊天平台。输入一段人格设定，AI 就按照该人格持续和你聊天。

## 快速上手（给AI和人）

1. **读 `AI_HANDOFF.md`** 了解项目全貌、架构、环境变量、已踩过的坑
2. **复制 `.env.example` 为 `.env`**，填入实际值（LLM API Key、数据库等）
3. **安装后端依赖**：`cd backend && pip install -r requirements.txt`
4. **安装前端依赖**：`cd frontend && npm install`
5. **启动后端**：`cd backend && python -m uvicorn app.main:app --reload --port 8000`
6. **启动前端**：`cd frontend && npm run dev`
7. **访问**：http://127.0.0.1:5173

> 生产环境：前端 Vercel + 后端 Render + 数据库 Supabase，push 到 main 自动部署。

## 核心特性

- **人格即文本**：直接输入一段人格描述，平台原样作为 system prompt 发送，不做任何改写、总结或附加规则
- **持续上下文**：AI 能看到人格 + 历史聊天记录 + 当前消息，保持人格一致
- **流式输出**：SSE 流式响应，逐字显示 AI 回答
- **多会话管理**：左侧聊天列表，支持新建、切换、删除、清空
- **人格可修改**：当前会话可随时编辑人格，新消息用新人格，历史记录不变
- **Markdown 渲染**：支持粗体、斜体、列表、代码块、引用等
- **深色模式**：一键切换
- **移动端适配**：响应式布局
- **API Key 安全**：Key 仅存在后端 .env，前端不可见

## 技术栈

- **前端**：React 18 + TypeScript + Vite + Tailwind CSS
- **后端**：Python + FastAPI + SQLAlchemy + SQLite
- **模型接口**：OpenAI-compatible Chat Completions API（支持 DeepSeek / Qwen / Doubao / OpenAI 等）

## 快速开始

### 1. 环境要求

- Python 3.10+
- Node.js 18+
- npm 9+

### 2. 配置 API

编辑项目根目录的 `.env` 文件：

```env
OPENAI_API_KEY=sk-你的APIKey
OPENAI_BASE_URL=https://api.deepseek.com/v1    # 按你的服务商填写
OPENAI_MODEL=deepseek-chat                       # 按你的服务商填写
DATABASE_URL=sqlite:///./data/app.db
```

> **重要**：`OPENAI_BASE_URL` 和 `OPENAI_MODEL` 必须填写，否则无法调用 AI。
>
> 常见服务商配置：
> - **DeepSeek**：`BASE_URL=https://api.deepseek.com/v1`，`MODEL=deepseek-chat`
> - **通义千问**：`BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`，`MODEL=qwen-plus`
> - **豆包**：`BASE_URL=https://ark.cn-beijing.volces.com/api/v3`，`MODEL=你的模型ID`
> - **OpenAI**：`BASE_URL=https://api.openai.com/v1`，`MODEL=gpt-4o-mini`

### 3. 启动（Windows）

双击 `start.bat`，自动安装依赖并启动前后端，浏览器自动打开。

或分别启动：

```bash
# 后端
start_backend.bat

# 前端（另开一个终端）
start_frontend.bat
```

### 4. 访问

打开浏览器访问：http://127.0.0.1:5173

## 开发模式

### 后端

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

API 文档：http://127.0.0.1:8000/docs

### 前端

```bash
cd frontend
npm install
npm run dev
```

## 生产构建

```bash
cd frontend
npm run build
```

构建产物在 `frontend/dist/`，可由后端或 Nginx 托管。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/conversations` | 创建会话 |
| GET | `/api/conversations` | 获取会话列表 |
| GET | `/api/conversations/{id}` | 获取会话详情 |
| PATCH | `/api/conversations/{id}` | 更新会话（人格/标题） |
| DELETE | `/api/conversations/{id}` | 删除会话 |
| GET | `/api/conversations/{id}/messages` | 获取消息列表 |
| DELETE | `/api/conversations/{id}/messages` | 清空会话消息 |
| POST | `/api/chat/stream` | 流式聊天（SSE） |

### 流式聊天请求

```json
POST /api/chat/stream
{
  "conversation_id": 1,
  "message": "你好"
}
```

响应为 SSE 流，每行格式：

```
data: {"type":"content","text":"你"}
data: {"type":"content","text":"好"}
data: {"type":"done"}
```

错误时：

```
data: {"type":"error","message":"API Key 无效，请检查配置。"}
```

## 目录结构

```
ai-persona-platform/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置管理
│   │   ├── database.py          # 数据库连接
│   │   ├── models/
│   │   │   └── conversation.py  # Conversation / Message 模型
│   │   ├── schemas/
│   │   │   └── conversation.py  # Pydantic 校验
│   │   ├── routers/
│   │   │   ├── conversations.py # 会话 CRUD 路由
│   │   │   └── chat.py          # 流式聊天路由
│   │   └── services/
│   │       ├── llm_client.py    # LLM 调用封装（含错误处理）
│   │       ├── conversation_service.py  # 会话业务逻辑
│   │       └── context_service.py       # 上下文裁剪
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Sidebar.tsx          # 聊天列表侧边栏
│   │   │   ├── PersonaSetup.tsx     # 人格设置页
│   │   │   ├── ChatArea.tsx         # 聊天主区域
│   │   │   ├── MessageList.tsx      # 消息列表
│   │   │   ├── MessageInput.tsx     # 输入框
│   │   │   └── EditPersonaModal.tsx # 编辑人格弹窗
│   │   ├── services/
│   │   │   └── api.ts               # API 客户端（含流式解析）
│   │   ├── types/
│   │   │   └── index.ts             # TypeScript 类型
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── tsconfig.json
├── data/                     # SQLite 数据库目录
├── .env                      # 环境变量（含 API Key，已 gitignore）
├── .env.example              # 环境变量模板
├── .gitignore
├── start.bat                 # 一键启动（Windows）
├── start_backend.bat         # 仅启动后端
├── start_frontend.bat        # 仅启动前端
└── README.md
```

## 常见错误

### "未配置 OPENAI_API_KEY"
检查 `.env` 文件中 `OPENAI_API_KEY` 是否填写。

### "未配置 OPENAI_MODEL"
检查 `.env` 文件中 `OPENAI_MODEL` 是否填写。

### "API Key 无效，请检查配置。"（401）
API Key 错误或已过期，检查 `.env` 中的 Key。

### "API 请求频率过高，请稍后再试。"（429）
请求过于频繁，等待后重试，或检查服务商配额。

### "模型不存在或 Base URL 错误"（404）
检查 `OPENAI_BASE_URL` 和 `OPENAI_MODEL` 是否与服务商匹配。

### "网络连接失败"
检查网络连接，或 Base URL 是否可访问。

### 前端页面空白
检查后端是否启动（http://127.0.0.1:8000/api/health 应返回 `{"status":"ok"}`）。

### 流式输出中断
网络不稳定或 API 服务端断开，重新发送即可。

## 人格设定原则

平台严格遵循以下原则：

1. **原样保存**：用户输入的人格文本完整保存到 `conversations.persona`
2. **原样发送**：作为 `system` 消息原样发送给 LLM，不做任何改写
3. **不附加规则**：平台不会自动添加安全人格、客服语气、拒答模板等额外内容
4. **不自动总结**：不会自动压缩、摘要或润色人格文本
5. **可随时修改**：编辑人格后，新消息使用新人格，历史消息不变

> 注意：第三方 API 服务商本身可能有安全策略，这是平台无法控制的。平台本身不额外制造人格限制。

## 上下文控制

当前版本使用简单策略：人格 + 最近 40 条消息。可在 `.env` 中调整：

```env
MAX_CONTEXT_MESSAGES=40
```

上下文裁剪逻辑在 `backend/app/services/context_service.py`，以后可扩展长期记忆 / RAG。

## 未来扩展

- 长期记忆系统
- RAG / 向量数据库
- 消息搜索
- 导出聊天记录
- 多模型切换
- 语音输入/输出
- 人格模板库（可选）

## 许可证

MIT
