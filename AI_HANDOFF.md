# AI 人格聊天平台 — AI 交接文档

> 本文档面向接管此项目的 AI 或开发者。读完即可直接上手，无需再猜。
> 最后更新：2026-09-03

---

## 一、项目一句话概述

一个支持多 AI 角色人格聊天的 Web 平台，用户可创建多个自定义人格角色，进行普通聊天 / 群聊 / 剧情模式对话，支持长期记忆、事实系统、图片生成、@角色、停止/暂停/继续等完整交互。当前处于 **Production Stable** 阶段，已上线生产环境。

---

## 二、当前状态（精确到 commit）

| 项目 | 值 |
|------|-----|
| 主分支 | `main` |
| 生产部署 commit | `2c28976`（Production Closure: 13/13全部通过） |
| 仓库最新 commit | `ea79bb8`（Production Stable 最终报告） |
| 当前工作分支 | `perf/chat-response-speed`（含未提交的性能优化代码，见下方说明） |
| 生产环境 | ✅ 运行中，13/13 测试通过 |
| Staging 环境 | ✅ 运行中 |

### 已完成的核心功能

- ✅ 多角色人格创建/编辑/删除/排序
- ✅ 普通聊天（指定角色 / @角色 / 智能选择）
- ✅ 群聊（所有角色依次发言）
- ✅ 剧情模式（启动 / 暂停 / 继续 / 停止 / 插话）
- ✅ 长期记忆系统（四层：User / Character / Relationship / Conversation）
- ✅ Canonical Facts 事实系统（confirmed / hypothesis / conflicted / superseded）
- ✅ 图片生成（GK Image 2.0，异步任务模式）
- ✅ SSE 流式输出
- ✅ 生成会话锁（同一 conversation 同时只能一个 active generation）
- ✅ Stop 真正取消（前端 AbortController + 后端 should_stop + LLM stream 取消）
- ✅ 多设备并发锁（内存锁 + 数据库唯一索引双重保障）
- ✅ 断线恢复（重新打开无重复消息）
- ✅ Supabase 认证 + 多用户数据隔离
- ✅ CORS 通过 FRONTEND_URL 环境变量管理
- ✅ 版本信息接口 `/api/version`
- ✅ 前端乐观更新（创建角色/会话立即显示，失败回滚）
- ✅ LLM 连接池优化（共享 AsyncOpenAI 客户端，应用生命周期复用）

### 未完成 / 待优化（P2，不影响使用）

- ⏳ Stop 延迟优化：生产环境 UI 停止延迟约 5 秒（本地仅 44ms，主要是 Render 网络+SSE 代理缓冲）
- ⏳ 长期记忆语义准确度优化：存在"考试"被理解为"面试"的语义漂移
- ⏳ 进入聊天加载速度优化：当前约 7 秒
- ⏳ Render 冷启动缓解：免费实例冷启动 5-30 秒
- ⏳ @多人并行生成：当前严格串行，角色2 等角色1 完全生成后才开始
- ⏳ 图片生成速度：GK Image 2.0 异步任务通常 30-90 秒

### 已知问题

- `perf/chat-response-speed` 分支有未提交的性能优化代码（LLM 连接池已实施但未部署验证），不要直接合并到 main，需先回归测试
- `APP_COMMIT` 环境变量在生产环境显示 "unknown"（未设置实际 commit hash）
- 角色记忆隔离和 Canonical Facts 冲突处理仅有单元测试，缺少完整 E2E 验证
- 长聊天 500 条以上的性能未做压力测试

---

## 三、技术架构（完整调用链）

### 前端调用链

```
App.tsx (入口, DEFAULT_USE_V2=true)
  └─ ChatPanelV2 (统一聊天面板, 三模式切换: 普通/群聊/剧情)
       └─ useChatV2 (状态管理 Hook)
            ├─ 乐观更新: 用户消息立即 append 到本地 state
            ├─ AbortController: 真正取消 fetch 请求
            ├─ 统一 SSE 事件处理: generation_started / character_started / content / character_completed / generation_completed / image_* / trace_data
            └─ api.chatV2Generate() → POST /api/chat/v2/generate (SSE 流)
```

### 后端调用链

```
main.py (FastAPI 入口, CORS, 静态文件, 路由注册)
  └─ routers/chat_v2.py (V2 统一接口: /generate /stop /pause /resume /status)
       └─ services/orchestrator.py (ConversationOrchestrator 统一调度器)
            ├─ plan(): 根据 mode/strategy 生成 ResponsePlan（确定 speakers 列表和顺序）
            ├─ ConversationLock: 会话级内存锁，同一 conversation 同时只能一个 active session
            ├─ GenerationSession: 生成会话生命周期管理（idle/running/paused/stopping/stopped/completed/error）
            └─ execute(): 按 plan.speakers 顺序逐个执行
                 └─ services/generation_executor.py (execute_character_generation)
                      ├─ context_service: 构建 prompt（人格 + 历史消息 + 记忆 + 事实）
                      ├─ memory_service: 异步提取长期记忆（不阻塞主回复）
                      ├─ fact_service: Canonical Facts 检索
                      ├─ image_service: 检测图片请求意图 → 调用 GK Image 2.0
                      └─ services/llm_client.py (chat_stream)
                           └─ 共享 AsyncOpenAI 客户端（连接池 keep-alive，应用生命周期单例）
                                └─ LLM API (OpenAI-compatible, 当前 DeepSeek)
```

### 旧接口兼容层

```
routers/chat.py (旧接口: /stream /reply-all /discussion /drama/*)
  └─ routers/legacy_compat.py (run_legacy_through_orchestrator)
       └─ 转换请求 → ConversationOrchestrator.execute_plan()
            └─ 转换 SSE 事件格式为旧格式（character_start→character_start, generation_completed→done 等）
```

> 旧接口保留作为回滚保险，内部全部转发到 Orchestrator，不再有独立逻辑。

### 数据库

**Supabase PostgreSQL**（生产）/ SQLite（本地开发），6 张核心表：

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `conversations` | 会话 | id, user_id, title, persona, scene, scene_time, scene_context |
| `characters` | 角色 | id, conversation_id, user_id, name, persona, sort_order |
| `messages` | 消息 | id, conversation_id, character_id, role, content, image_url, generation_id, sequence_number, parent_message_id, message_type |
| `generation_sessions` | 生成会话 | generation_id(唯一), conversation_id, mode, strategy, status, speakers, stop_requested, pause_requested, drama_config |
| `facts` | 规范事实 | id, user_id, conversation_id, character_id, subject, content, fact_type, status(confirmed/uncertain/conflicted/superseded), confidence |
| `memories` | 长期记忆 | id, user_id, conversation_id, character_id, content, memory_type, importance, is_active, last_used_at |

**关键索引**：
- `generation_sessions`: 部分唯一索引 `idx_active_generation_per_conversation`（同一 conversation 同时只能一个 status in running/paused/stopping）
- `messages.generation_id`: 普通索引

### 部署架构

```
用户浏览器
  └─ Vercel (前端静态托管, React + Vite)
       └─ HTTPS API 请求
            └─ Render (后端, FastAPI + Uvicorn, 免费实例)
                 ├─ Supabase (PostgreSQL 数据库 + Auth)
                 ├─ LLM API (DeepSeek, OpenAI-compatible)
                 └─ GK Image 2.0 (小羽毛AI聚合平台, 图片生成)
```

### 图片生成架构

GK Image 2.0（小羽毛AI聚合平台），异步任务模式：
1. `detect_image_request()`: 关键词匹配检测用户是否请求图片
2. `build_image_prompt()`: 从角色人格提取外貌关键词，构建英文 prompt
3. `_gk_create_task()`: POST `/v1/media/generate` 创建任务，获取 task_id
4. `_gk_poll_task()`: 每 4 秒轮询 `/v1/media/status`，直到 is_final=true
5. `_download_image()`: 下载 result_url 到本地 `data/generated_images/`
6. 返回 `/static/images/xxx.png`（下载失败则 fallback 返回远程 URL，不中断聊天）

---

## 四、环境变量清单（最关键）

### 后端环境变量（配置在 Render）

| 变量名 | 用途 | 是否敏感 | 默认值/示例 |
|--------|------|----------|-------------|
| `OPENAI_API_KEY` | LLM API 密钥 | ✅ 敏感 | `sk-xxx`（DeepSeek） |
| `OPENAI_BASE_URL` | LLM API 基础地址 | ❌ | `https://api.deepseek.com/v1` |
| `OPENAI_MODEL` | LLM 模型名 | ❌ | `deepseek-chat` |
| `DATABASE_URL` | 数据库连接串 | ✅ 敏感 | `postgresql://user:pass@host:5432/db`（生产 Supabase）/ `sqlite:///./data/app.db`（本地） |
| `USE_SUPABASE` | 是否启用 Supabase 模式 | ❌ | `true`（生产）/ `false`（本地免登录） |
| `SUPABASE_URL` | Supabase 项目 URL | ❌ | `https://xxx.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase 匿名 Key | ⚠️ 半敏感（前端可见） | `eyJhbGci...` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase 服务角色 Key（后端直连DB用） | ✅ 敏感 | `eyJhbGci...` |
| `FRONTEND_URL` | CORS 允许的前端地址 | ❌ | `https://ai-persona-chat-mu.vercel.app` |
| `IMAGE_API_BASE_URL` | 图片生成 API 基础地址 | ❌ | `https://api.lk888.ai` |
| `IMAGE_API_KEY` | 图片生成 API Key | ✅ 敏感 | 小羽毛AI聚合平台 Key |
| `IMAGE_MODEL` | 图片生成模型名 | ❌ | `gk-image-2.0` |
| `IMAGE_OUTPUT_DIR` | 图片输出目录 | ❌ | `data/generated_images` |
| `IMAGE_TIMEOUT` | 图片生成超时（秒） | ❌ | `180` |
| `APP_ENVIRONMENT` | 运行环境标识 | ❌ | `production` / `staging` / `development` |
| `APP_VERSION` | 版本号 | ❌ | `Chat Core 2.0` |
| `APP_COMMIT` | 部署 commit hash | ❌ | `2c28976`（当前显示 unknown） |
| `MAX_CONTEXT_MESSAGES` | 上下文最大消息数 | ❌ | `40` |
| `LLM_TIMEOUT` | LLM 请求超时（秒） | ❌ | `120` |
| `RATE_LIMIT_PER_MINUTE` | 每分钟限流 | ❌ | `60` |
| `DOUBAO_VISION_API_KEY` | 【Legacy】豆包视觉 Key（回滚备用） | ✅ 敏感 | 留空即可 |
| `DOUBAO_VISION_BASE_URL` | 【Legacy】豆包视觉地址 | ❌ | `https://ark.cn-beijing.volces.com/api/v3` |
| `DOUBAO_VISION_MODEL` | 【Legacy】豆包视觉模型接入点 ID | ❌ | 留空即可 |

### 前端环境变量（配置在 Vercel）

| 变量名 | 用途 | 是否敏感 | 默认值/示例 |
|--------|------|----------|-------------|
| `VITE_USE_SUPABASE` | 是否启用 Supabase 认证 | ❌ | `true`（生产）/ `false`（本地免登录） |
| `VITE_SUPABASE_URL` | Supabase 项目 URL | ❌ | `https://xxx.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Supabase 匿名 Key | ⚠️ 半敏感 | `eyJhbGci...` |
| `VITE_API_BASE_URL` | 后端 API 地址 | ❌ | `https://ai-persona-backend-znpi.onrender.com/api`（生产） |

> ⚠️ **绝对不要**把 `OPENAI_API_KEY`、`SUPABASE_SERVICE_ROLE_KEY`、`IMAGE_API_KEY` 等后端 Secret 配置到前端 `VITE_*` 变量中。Vite 会把 `VITE_*` 变量打包进前端 bundle，任何人都能看到。

---

## 五、关键文件地图

### 后端核心

| 功能 | 文件路径 | 说明 |
|------|----------|------|
| 应用入口 | `backend/app/main.py` | FastAPI 入口，CORS，路由注册，健康检查，版本接口 |
| 配置管理 | `backend/app/config.py` | 所有环境变量读取，Settings 单例 |
| 数据库连接 | `backend/app/database.py` | SQLAlchemy engine + SessionLocal |
| 数据模型 | `backend/app/models/conversation.py` | Conversation / Character / Message / GenerationSession / Fact / Memory 6 个模型 |
| 数据库迁移 | `backend/app/migrations.py` | 启动时自动执行，增量 ALTER TABLE，不 DROP 不清空 |
| **聊天内核调度器** | `backend/app/services/orchestrator.py` | **核心中的核心**：ConversationOrchestrator，ResponsePlan，GenerationSession，ConversationLock |
| **生成执行器** | `backend/app/services/generation_executor.py` | 单角色生成执行：上下文构建→LLM调用→图片检测→SSE推送→消息保存 |
| **LLM 客户端** | `backend/app/services/llm_client.py` | 共享 AsyncOpenAI 连接池，chat_stream 流式生成 |
| **图片生成** | `backend/app/services/image_service.py` | GK Image 2.0 异步任务模式，关键词检测，prompt构建，下载+fallback |
| 记忆系统 | `backend/app/services/memory_service.py` | 四层记忆提取和存储，异步执行不阻塞主回复 |
| 事实系统 | `backend/app/services/fact_service.py` | Canonical Facts 检索和管理 |
| 上下文服务 | `backend/app/services/context_service.py` | 构建 LLM prompt：人格+历史+记忆+事实 |
| 智能路由 | `backend/app/services/router_service.py` | 智能模式下决定谁该说话 |
| 生成会话服务 | `backend/app/services/generation_session_service.py` | generation_sessions 表的 CRUD |
| 会话服务 | `backend/app/services/conversation_service.py` | 会话/角色/消息的业务逻辑 |
| 停止标志 | `backend/app/services/stop_flags.py` | 全局停止标志管理 |
| 性能追踪 | `backend/app/services/trace.py` | RequestTrace 类，T0~T16 全链路时间点 |
| V2 聊天路由 | `backend/app/routers/chat_v2.py` | `/api/chat/v2/generate|stop|pause|resume|status` |
| 旧接口路由 | `backend/app/routers/chat.py` | 旧接口，内部转发到 legacy_compat |
| 旧接口兼容层 | `backend/app/routers/legacy_compat.py` | 将旧接口请求转换为 Orchestrator 调用 |
| 会话路由 | `backend/app/routers/conversations.py` | 会话 CRUD |
| 角色路由 | `backend/app/routers/characters.py` | 角色 CRUD + 记忆接口 |

### 前端核心

| 功能 | 文件路径 | 说明 |
|------|----------|------|
| 应用入口 | `frontend/src/App.tsx` | 根组件，默认使用 ChatPanelV2，乐观更新，V1 旧逻辑保留作回滚 |
| **聊天面板 V2** | `frontend/src/components/ChatPanelV2.tsx` | **生产默认聊天面板**，三模式切换，@角色菜单，剧情控制 |
| **状态管理 Hook** | `frontend/src/hooks/useChatV2.ts` | **核心**：乐观更新，SSE 事件处理，AbortController，性能 Trace |
| API 客户端 | `frontend/src/services/api.ts` | 所有 API 调用，SSE 解析，chatV2Generate 等 |
| 认证上下文 | `frontend/src/contexts/AuthContext.tsx` | Supabase 认证状态管理 |
| 认证服务 | `frontend/src/services/auth.ts` | Supabase Auth 封装 |
| 类型定义 | `frontend/src/types/index.ts` | TypeScript 类型，含 PerfTraceData |
| 侧边栏 | `frontend/src/components/Sidebar.tsx` | 会话列表 |
| 角色设置 | `frontend/src/components/CharacterSetup.tsx` | 角色创建/编辑/删除/排序 |
| 旧聊天面板 | `frontend/src/components/ChatArea.tsx` | V1 旧面板，保留作回滚保险 |

### 配置和部署

| 文件 | 说明 |
|------|------|
| `backend/requirements.txt` | Python 依赖（fastapi, sqlalchemy, openai, httpx, supabase, psycopg2-binary 等） |
| `backend/Dockerfile` | Render 部署用 Dockerfile |
| `frontend/package.json` | 前端依赖（react 18, vite 5, tailwind, @supabase/supabase-js） |
| `frontend/vite.config.ts` | Vite 配置 |
| `frontend/vercel.json` | Vercel 部署配置 |
| `.env.example` | 环境变量模板（根目录） |
| `.gitignore` | Git 忽略规则 |

---

## 六、已踩过的坑（最有价值的部分）

### 1. Render 免费实例冷启动 5-30 秒

**现象**：用户首次访问后端 API 时，响应极慢（5-30秒），之后恢复正常。
**原因**：Render 免费实例在无流量 15 分钟后会休眠，下次请求需要冷启动（Python 启动 + 依赖加载 + 实例分配）。
**解决方案**：这是基础设施问题，代码无法完全解决。可选方案：升级 Render 付费计划 / 定时 ping 健康检查端点 / 迁移到常驻服务器。当前接受此限制。

### 2. SQLite 相对路径在 Render 工作目录不同导致 500

**现象**：本地开发正常，部署到 Render 后数据库操作报 500，提示找不到数据库文件。
**原因**：`DATABASE_URL=sqlite:///./data/app.db` 的相对路径基于进程工作目录，Render 的工作目录和本地不同。
**解决方案**：生产环境使用 Supabase PostgreSQL，`DATABASE_URL` 配置为完整的 PostgreSQL 连接串。本地开发才用 SQLite。

### 3. Render API 更新环境变量的 PUT 格式问题

**现象**：通过 Render API 更新环境变量时，PUT 请求返回 400 或变量未更新。
**原因**：Render API 的 env vars 更新需要特定格式，不是简单的 key-value JSON，且需要包含所有现有变量（全量替换而非增量）。
**解决方案**：使用 Render 控制台手动更新环境变量，或使用 `render` CLI。如果用 API，先 GET 现有变量，修改后 PUT 全量。

### 4. 图片下载失败不能让整个聊天 500

**现象**：图片生成成功但下载到本地时网络失败，导致整个聊天接口返回 500。
**原因**：`_download_image()` 抛出异常未被捕获，冒泡到 SSE 流导致连接断开。
**解决方案**：在 `generate_image()` 中，下载失败时 catch 异常，直接返回远程 URL（`result_url`），不中断聊天。前端 `resolveImageUrl()` 能正确处理远程 URL 和本地路径。

### 5. @多人必须传 strategy="mention"

**现象**：前端传了 `mentioned_character_ids` 但后端只回复了第一个角色，或回复了错误的角色。
**原因**：Orchestrator 的 `plan()` 方法根据 `strategy` 字段决定如何确定 speakers。如果 `strategy="specific"`，即使传了 `mentioned_character_ids` 也会被忽略，只用 `specified_character_id`。
**解决方案**：@多人时前端必须传 `strategy: "mention"` 和 `mentioned_character_ids: [id1, id2]`。ChatPanelV2 中已正确处理（检测到 @角色名时自动设置 strategy=mention）。

### 6. Stop 5 秒延迟是 LLM 流取消 + 网络延迟，不是代码 bug

**现象**：用户点击 Stop 后，UI 上停止按钮约 5 秒后才消失，内容停止增长。
**原因**：本地测试 Stop 延迟仅 44ms（P50）。生产环境的 5 秒由以下构成：前端 Stop 请求 → Render 网络延迟 → 后端设置 should_stop → LLM HTTP stream 取消（当前 chunk 完成后才取消）→ SSE 代理缓冲刷新 → 前端 UI 更新。主要瓶颈是 Render 网络和 SSE 代理缓冲。
**解决方案**：功能语义成立（内容确实停止增长），体感偏慢。P2 优化项，可考虑 asyncio.Event 替代 50ms 轮询、减少 SSE 缓冲。

### 7. LLM 连接池优化（419ms → ~80ms 预期）

**现象**：每次 LLM 请求都要 DNS + TLS + TCP 连接建立，P50 耗时 419ms，冷启动首次 862ms。
**原因**：旧代码每次调用 `chat_stream()` 都新建 `AsyncOpenAI` 客户端，`finally` 中 `await client.close()`，连接不复用。
**解决方案**：改为应用生命周期共享单例 `_shared_client`，不关闭客户端。AsyncOpenAI 内部 httpx 默认带连接池（max_connections=100, max_keepalive=20），连接自动复用。代码已在 `perf/chat-response-speed` 分支实施，预期 LLM 连接降至 50-80ms，TTFT 降低约 26%。**尚未部署验证，合并前必须回归测试。**

### 8. 前端乐观更新必须有失败回滚

**现象**：创建角色时点击保存，UI 立即显示新角色，但如果 API 失败，假角色永久存在。
**原因**：乐观更新只做了"立即显示"，没有做"失败回滚"。
**解决方案**：所有乐观更新（创建会话、创建角色、编辑角色、删除角色、排序、删除会话）都必须：1) 保存原始值；2) 立即更新 UI；3) API 成功后替换为真实对象；4) API 失败后回滚到原始值。App.tsx 中所有 handle* 函数都已实现此模式。

### 9. 沙箱 .git 权限问题

**现象**：在 AI 沙箱环境中执行 `git commit` 或 `git push` 时报权限错误或 .git 目录不可写。
**原因**：沙箱环境可能限制 .git 目录的写入权限。
**解决方案**：使用 GitHub API（通过 `curl` 或 `gh` CLI）创建 commit 和 push，或在正常环境中执行 git 操作。本项目的 perf 分支代码就是因为沙箱 .git 权限问题而未提交。

### 10. CORS 不能硬编码多个 URL

**现象**：生产环境 CORS 报错，或 Staging 环境无法访问生产后端。
**原因**：旧代码硬编码了多个允许的 origin（生产 + 多个 Staging URL），维护困难且不安全。
**解决方案**：通过 `FRONTEND_URL` 环境变量管理 CORS。生产环境只允许正式前端 `https://ai-persona-chat-mu.vercel.app`。Staging 环境配置自己的 `FRONTEND_URL`。未设置时默认生产前端。

---

## 七、已验证 vs 未验证

### ✅ 已验证（有真实测试数据，生产环境）

| 测试项 | 结果 | 数据 |
|--------|------|------|
| 注册登录 | ✅ PASS | 注册成功，自动登录 |
| 新建聊天 | ✅ PASS | 3072ms |
| 创建角色 | ✅ PASS | API=4650ms，UI即时响应（乐观更新） |
| 普通聊天 | ✅ PASS | 20564ms（含AI生成时间） |
| 快速连点防重复 | ✅ PASS | 快速点击5次，发送按钮被禁用，无重复生成 |
| @单人 | ✅ PASS | 正确角色回复 |
| @多人 | ✅ PASS | 小雅→小王，顺序正确，无乱序 |
| 群聊 | ✅ PASS | 所有角色依次发言，顺序正确 |
| 智能模式 | ✅ PASS | 智能路由选择正确角色 |
| 剧情启动 | ✅ PASS | 剧情正常启动 |
| 剧情 Pause/Resume | ✅ PASS | 暂停后继续正常 |
| 剧情 Stop | ✅ PASS | 停止后不再生成 |
| Stop 功能 | ✅ PASS | UI停止延迟=5467ms，内容已停止增长 |
| 长期记忆跨聊天 | ✅ PASS | 跨聊天记忆检索成功（找到下周相关信息） |
| 图片生成（GK） | ✅ PASS | 生产环境图片生成成功，图片元素数量=1 |
| 多设备并发锁 | ✅ PASS | 生成中发送按钮被禁用，generation lock生效 |
| 断线恢复 | ✅ PASS | 重新打开后聊天界面正常，无重复消息 |
| CORS | ✅ PASS | 通过 FRONTEND_URL 管理，只允许正式前端 |
| Production Version | ✅ PASS | environment=production, chat_core=2.0 |
| 多用户数据隔离 | ✅ PASS | 不同用户数据完全隔离 |
| 前端无 Secret | ✅ PASS | 前端 bundle 不包含 API Key |

**三轮测试汇总**：RC-3 Staging 11/11 ✅ + Production Smoke 9/10 ✅ + Production Closure 13/13 ✅

### ⏳ 未充分验证

| 项目 | 状态 | 说明 |
|------|------|------|
| 角色记忆隔离 E2E | ⏳ 未验证 | 代码实现了 character_id 过滤，但缺少完整 E2E 测试确认角色A看不到角色B的记忆 |
| Canonical Facts 冲突处理 E2E | ⏳ 未验证 | 事实状态机（confirmed/uncertain/conflicted/superseded）有单元测试，但缺少 E2E 验证冲突场景 |
| 长聊天 500条以上性能 | ⏳ 未压测 | 上下文裁剪为最近40条，但消息列表加载、DB 查询在大数据量下未测试 |
| @多人并行生成 | ⏳ 未实现 | 当前严格串行，角色2等角色1完全生成。并行化是 P1 优化项，未实施 |
| LLM 连接池优化效果 | ⏳ 待验证 | 代码已在 perf 分支实施，预期 TTFT 降低 26%，但尚未部署到生产验证 |
| 图片生成降级重试 | ⏳ 部分验证 | 代码实现了 fallback_prompt 重试，但生产环境未触发过降级场景 |

---

## 八、常用命令

### 本地启动

```bash
# 后端
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev
```

或 Windows 一键启动：双击 `start.bat`

### 访问地址

| 环境 | 前端 | 后端 |
|------|------|------|
| 本地 | http://127.0.0.1:5173 | http://127.0.0.1:8000 |
| 生产 | https://ai-persona-chat-mu.vercel.app | https://ai-persona-backend-znpi.onrender.com |
| Staging | https://ai-persona-chat-qkito1k5p-ai-persona-team.vercel.app | https://ai-persona-backend-staging.onrender.com |

### 健康检查和版本

```bash
# 健康检查
curl https://ai-persona-backend-znpi.onrender.com/health
# 返回: {"status":"ok","mode":"supabase"}

# 版本信息
curl https://ai-persona-backend-znpi.onrender.com/api/version
# 返回: {"version":"Chat Core 2.0","commit":"unknown","environment":"production","app_name":"AI 人格聊天平台","chat_core":"2.0"}

# API 文档（本地）
# http://127.0.0.1:8000/docs
```

### 部署

- **前端**：push 到 `main` 分支，Vercel 自动部署
- **后端**：push 到 `main` 分支，Render 自动部署
- **Staging**：push 到 `staging/chat-core-2.0` 分支

### Git 仓库

https://github.com/wujinbi006-svg/ai-persona-chat

### 数据库

```bash
# 本地 SQLite 数据库位置
backend/data/app.db

# 生产 Supabase 控制台
# https://supabase.com/dashboard/project/<project-id>
```

---

## 九、后续方向（用户明确说过的）

### P2 优化项（可做，但不急）

1. **Stop 延迟优化**：当前生产约 5 秒（本地 44ms），功能语义成立但体感偏慢。可优化 LLM stream 取消逻辑、减少 SSE 代理缓冲。
2. **长期记忆语义准确度优化**：存在"考试"被理解为"面试"的语义漂移。需要优化记忆检索的语义匹配算法。
3. **进入聊天加载速度优化**：当前约 7 秒。可优化界面切换和数据加载（缓存、懒加载）。
4. **Render 冷启动缓解**：免费实例冷启动 5-30 秒。可考虑定时 ping / 升级付费 / 迁移服务器。

### 不要做（用户明确禁止）

- ❌ **大规模重构 Chat Core**：系统已稳定，不要再大改架构。先让系统稳定运行，用真实用户数据指导优化方向。
- ❌ **新增功能**：当前阶段不新增功能，只做 Bug 修复和 P2 性能优化。
- ❌ **换模型**：当前使用 DeepSeek，不要随意更换 LLM 模型。
- ❌ **删除 V1 旧代码**：`ChatArea.tsx`、旧接口路由、`legacy_compat.py` 等 V1 代码保留作为回滚保险，不要删除。
- ❌ **删除豆包视觉旧实现**：`_generate_image_doubao_legacy()` 保留作为图片生成的回滚备用。

---

## 十、用户偏好（别的 AI 不知道这些，必须遵守）

1. **讨厌"理论上应该可以"**：必须有真实测试数据。不要说"应该能工作"、"理论上没问题"，要说"已验证通过，数据是 XXX"。
2. **讨厌"代码完成=任务完成"**：必须生产环境验证。代码写完不算完成，必须部署到生产/Staging 并实际测试通过才算完成。
3. **授权自动执行**：用户授权 AI 自动执行普通 git/deploy/test 操作，不要把这些操作丢给用户手动做。直接执行，遇到阻塞再报告。
4. **遇到沙箱限制换工具**：如果沙箱环境限制了 .git 写入、Python 执行等，不要死磕。换用 GitHub API、`gh` CLI、Render API 等替代方案。
5. **性能优化必须先测 baseline 再定位瓶颈**：不要凭感觉改代码。先跑 baseline 测试，用数据定位瓶颈，再针对性优化。本项目的 perf_baseline.py 可用于基线测试。
6. **每次修改必须回归测试**：不能为了速度破坏功能。任何代码修改后必须回归测试核心功能（普通聊天、@多人、Stop、图片生成等），确认无退化。
7. **乐观更新必须有失败回滚**：任何前端乐观更新必须实现失败回滚逻辑，不能让假数据永久存在。保存原始值 → 立即更新 → 成功替换 → 失败回滚。

---

## 附录：快速排查清单

| 症状 | 可能原因 | 排查步骤 |
|------|----------|----------|
| 前端页面空白 | 后端未启动 / CORS 报错 | 检查 `https://<backend>/health`，浏览器 Console 看 CORS 错误 |
| 聊天一直"生成中" | Render 冷启动 / LLM API 超时 | 等 30 秒重试，检查后端日志 |
| 回复为空 | LLM API Key 无效 / 模型名错误 | 检查 `OPENAI_API_KEY` 和 `OPENAI_MODEL`，调用 `/api/version` 确认环境 |
| 图片不显示 | 图片下载失败 / 静态文件路径错 | 检查图片 URL 是否为远程 URL（fallback），检查 `/static/images/` 是否可访问 |
| 500 错误 | 数据库连接失败 / 代码异常 | 查看 Render 日志，确认 `DATABASE_URL` 正确 |
| 401 未授权 | Supabase token 过期 | 重新登录，检查 `VITE_USE_SUPABASE` 配置 |
| Stop 无效 | 旧版前端未用 V2 / 后端锁冲突 | 确认使用 ChatPanelV2，检查 generation session 状态 |

---

*文档结束。如有疑问，先查本文档，再查 `CHAT_CORE_2.0_PRODUCTION_STABLE_REPORT.md` 和 `PHASE2_OPTIMIZATION_REPORT.md`。*
