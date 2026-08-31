# Chat Core 2.0 RC-3 Staging 部署进度报告

**分支**: `staging/chat-core-2.0`
**最新 commit**: `5e15e26`
**报告日期**: 2026-08-31
**状态**: Vercel Staging 已部署，Render Staging 和环境变量待配置

---

## 一、已完成 ✅

### 1. Vercel Staging 前端部署 ✅

- **部署方式**: Vercel CLI 自动部署
- **Preview URL**: https://ai-persona-chat-lm2nlumr7-ai-persona-team.vercel.app
- **部署状态**: Ready
- **构建时间**: 15 秒
- **前端访问验证**: ✅ 200 OK，页面长度 340867 bytes
- **Vercel 项目**: ai-persona-team/ai-persona-chat
- **部署分支**: staging/chat-core-2.0

### 2. 代码准备 ✅

- staging 分支已创建并合并 RC-2 所有代码（20个文件，4629行新增）
- /api/version 接口已添加（版本号/commit/环境标识）
- 本地构建验证通过（前端 build 成功，后端启动无 import error）
- 数据库 migration 检查通过（所有表和字段都存在，唯一索引已创建）
- 代码已推送到 GitHub（staging/chat-core-2.0 分支，commit 5e15e26）

### 3. Vercel CLI 配置 ✅

- Vercel CLI 已安装（版本 59.9.1）
- Vercel CLI 已登录（用户 wujinbi006-svg）
- Vercel 项目已链接（ai-persona-team/ai-persona-chat）

---

## 二、待完成 ⏳

### 1. Render Staging 后端部署 ⏳（需要手动配置）

**问题**: Render CLI 未安装，且没有 Render API Key，无法自动创建 Render Staging 服务。

**手动配置步骤**:

1. 登录 Render Dashboard: https://dashboard.render.com
2. 点击 **New + → Web Service**
3. 连接 GitHub 仓库 `wujinbi006-svg/ai-persona-chat`
4. 选择分支 `staging/chat-core-2.0`
5. 配置:
   - **Name**: `ai-persona-backend-staging`
   - **Runtime**: Python 3
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free（或 Starter）
6. 配置环境变量（见下方"环境变量配置"）
7. 点击 **Create Web Service**
8. 等待部署完成

### 2. Vercel Staging 环境变量配置 ⏳（需要手动配置）

**问题**: Vercel 项目缺少前端需要的 VITE_* 环境变量。当前环境变量主要是后端相关的（DATABASE_URL、OPENAI_API_KEY 等），没有前端需要的 VITE_USE_SUPABASE、VITE_SUPABASE_URL、VITE_SUPABASE_ANON_KEY、VITE_API_BASE_URL。

**手动配置步骤**:

1. 登录 Vercel Dashboard: https://vercel.com/dashboard
2. 进入项目 `ai-persona-chat`
3. 进入 **Settings → Environment Variables**
4. 添加以下环境变量（选择 Preview 环境，避免影响 Production）:

| 变量名 | 值 | 环境 |
|--------|-----|------|
| `VITE_USE_SUPABASE` | `true` | Preview |
| `VITE_SUPABASE_URL` | `https://hduxrpsfgacdthgpdjxk.supabase.co` | Preview |
| `VITE_SUPABASE_ANON_KEY` | `<你的 Supabase anon key>` | Preview |
| `VITE_API_BASE_URL` | `<Render Staging 后端 URL>/api` | Preview |

5. 保存后，重新部署 Vercel Staging（触发新的 Preview 部署）

**注意**:
- `VITE_SUPABASE_ANON_KEY` 需要从 Supabase Dashboard 获取（Settings → API → Project API keys → anon public）
- `VITE_API_BASE_URL` 需要等 Render Staging 部署完成后，使用 Render Staging 的 URL
- 如果暂时不想创建独立的 Render Staging，可以先使用现有的 Render 生产后端 URL: `https://ai-persona-backend-znpi.onrender.com/api`

### 3. 环境变量配置（Render Staging）

Render Staging 后端需要配置以下环境变量:

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `USE_SUPABASE` | `true` | 启用 Supabase 模式 |
| `SUPABASE_URL` | `https://hduxrpsfgacdthgpdjxk.supabase.co` | Supabase 项目 URL |
| `SUPABASE_ANON_KEY` | `<你的 Supabase anon key>` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | `<你的 Supabase service role key>` | Supabase service role key |
| `DATABASE_URL` | `<你的 Supabase 数据库连接字符串>` | Supabase PostgreSQL 连接字符串 |
| `OPENAI_API_KEY` | `<你的 AI API key>` | AI API key |
| `OPENAI_BASE_URL` | `<你的 AI API base URL>` | AI API base URL |
| `OPENAI_MODEL` | `<你的 AI 模型名称>` | AI 模型名称 |
| `FRONTEND_URL` | `<Vercel Staging 前端 URL>` | Vercel Staging 前端 URL（用于 CORS） |
| `APP_VERSION` | `Chat Core 2.0 RC-3` | 应用版本号 |
| `APP_COMMIT` | `5e15e26` | 当前 commit hash |
| `APP_ENVIRONMENT` | `staging` | 环境标识 |

**注意**:
- 敏感信息（API Key、数据库密码等）需要从现有生产环境或相应平台获取
- 如果暂时不想创建独立的 Supabase Staging 数据库，可以先使用现有的生产数据库（确保 migration 是安全的，只 ALTER/CREATE，不 DROP/TRUNCATE）
- `FRONTEND_URL` 需要使用 Vercel Staging 的 URL: `https://ai-persona-chat-lm2nlumr7-ai-persona-team.vercel.app`

---

## 三、Supabase Auth 配置

如果使用独立的 Vercel Staging 前端 URL，需要在 Supabase Auth 配置中添加 Staging URL:

1. 登录 Supabase Dashboard: https://supabase.com/dashboard
2. 进入项目 `hduxrpsfgacdthgpdjxk`
3. 进入 **Authentication → URL Configuration**
4. 在 **Redirect URLs** 中添加:
   - `https://ai-persona-chat-lm2nlumr7-ai-persona-team.vercel.app/**`
5. 保存设置

**注意**: 不要删除现有的生产 URL 配置，只添加 Staging URL。

---

## 四、部署验证清单

配置完成后，验证以下项目:

### 1. 后端验证
```bash
# 健康检查
curl https://<render-staging-url>.onrender.com/health
# 期望: {"status":"ok","mode":"supabase"}

# 版本检查
curl https://<render-staging-url>.onrender.com/api/version
# 期望: {"version":"Chat Core 2.0 RC-3","commit":"5e15e26","environment":"staging",...}
```

### 2. 前端验证
- 访问 https://ai-persona-chat-lm2nlumr7-ai-persona-team.vercel.app
- 确认页面正常加载，包含登录/注册界面
- 打开浏览器开发者工具，检查 Network 请求是否正常
- 确认 API 请求指向 Render Staging 后端

### 3. 前后端版本一致
- Vercel Staging 代码 commit = 5e15e26
- Render Staging 代码 commit = 5e15e26
- /api/version 返回 commit = 5e15e26
- 三个必须一致

---

## 五、公网 E2E 测试清单

部署验证完成后，执行以下核心测试（详细测试步骤请参考 `CHAT_CORE_2.0_RC2_REPORT.md`）:

### 核心验收指标（用户最关注的 7 个问题）

1. **新角色能不能立即出现**
   - 点击保存角色后，角色应立即出现在 UI（目标 <1秒）
   - 记录实际耗时: API ms + UI ms

2. **一句话会不会莫名其妙回两次**
   - 发送一条消息，只产生 1 个 generation 和 1 个 AI 回复
   - 快速连点发送 ×5，仍然只有 1 个 generation
   - 检查 Network: 一次用户点击只产生一个 /api/chat/v2/generate 请求

3. **@两个人会不会乱序**
   - 输入 @小雅 @小王 你们好
   - 严格按照 小雅 → 小王 顺序回复
   - 即使人为制造网络速度差（小雅慢、小王快），最终显示仍然是 小雅 → 小王

4. **按停止以后真的停**
   - 发送较长 prompt，生成过程中点击停止
   - 记录 stop_click → generation_stopped 的实际毫秒数（目标 <500ms）
   - 停止后等待 10 秒，没有第二条 AI、没有下一角色、没有图片、没有剧情继续

5. **剧情真的能停**
   - 进入剧情模式，确认持续运行（不是固定轮数）
   - 点击停止，等待 10 秒，绝对没有后续消息
   - 两个 conversation 同时剧情，停止 A，B 不受影响

6. **隔天回来角色还认识我**
   - Chat A: 告诉角色"我下周考试"
   - 创建 Chat B: 询问"你还记得我要考试吗？"
   - 确认角色能够从长期记忆中检索到相关信息
   - 检查 Canonical Facts: 事实与假设分离，不会自动覆盖

7. **手机和电脑同时用不会打架**
   - 电脑登录测试账号，开始生成
   - 手机同账号登录，尝试生成
   - 确认不会出现第二个 active generation
   - 双用户测试: A 和 B 完全隔离

### 其他测试项目

- 普通聊天: PASS/FAIL
- 智能模式: PASS/FAIL
- 群聊: PASS/FAIL
- 剧情暂停/继续: PASS/FAIL
- 角色记忆隔离: PASS/FAIL
- 图片生成: PASS/FAIL
- 图片 Stop: PASS/FAIL
- 网络断开恢复: PASS/FAIL
- V1 回滚: PASS/FAIL
- 数据一致性（无重复消息/无孤儿 generation）: PASS/FAIL

---

## 六、staging → main 合并条件

只有以下条件全部满足，才允许将 `staging/chat-core-2.0` 合并到 `main`:

1. ✅ Vercel Staging 部署成功并可访问
2. ✅ Render Staging 部署成功并可访问
3. ✅ 环境变量配置正确（前端 VITE_*、后端 Supabase/AI API）
4. ✅ /api/version 返回正确的版本信息
5. ✅ 前后端 commit 一致
6. ✅ 核心验收指标（7个用户最关注的问题）全部 PASS
7. ✅ 其他测试项目通过率 >95%
8. ✅ 无 P0 问题（不影响核心功能的严重 bug）
9. ✅ 性能数据已记录（实际毫秒数）
10. ✅ V1 回滚测试通过
11. ✅ 数据一致性验证通过（无重复消息/无孤儿 generation）

---

## 七、风险提示

### 1. Render 免费实例休眠
- Render 免费实例会在 15 分钟无请求后休眠
- 第一次访问可能需要 30-60 秒唤醒
- 这不是 bug，是 Render 免费计划的限制
- E2E 测试时先访问 /health 唤醒实例

### 2. 数据库 migration 风险
- 当前 migration 只包含 ALTER/CREATE 操作，不包含 DROP/TRUNCATE
- 但是，如果 staging 环境使用生产数据库，migration 仍然会影响生产数据
- 建议创建独立的 Supabase Staging 数据库进行测试

### 3. 环境变量配置
- Staging 环境需要配置与生产环境相同的环境变量
- 特别是 SUPABASE_URL、SUPABASE_ANON_KEY、SUPABASE_SERVICE_ROLE_KEY、DATABASE_URL
- 敏感信息（API Key、数据库密码等）需要从现有生产环境或相应平台获取

### 4. CORS 配置
- Render Staging 的 FRONTEND_URL 需要配置为 Vercel Staging 的 URL
- 否则前端请求会被 CORS 策略阻止

---

## 八、总结

**已完成**:
- Vercel Staging 前端部署成功（Preview URL 可访问）
- 代码准备完成（staging 分支、/api/version 接口、本地构建验证）
- Vercel CLI 配置完成（已登录、已链接项目）

**待完成**:
- Render Staging 后端部署（需要手动在 Render Dashboard 创建）
- Vercel Staging 环境变量配置（需要手动添加 VITE_* 环境变量）
- Supabase Auth 配置（需要添加 Staging URL 到 Redirect URLs）
- 公网 E2E 测试（54项，需要部署完成后执行）

**建议下一步**:
1. 按照本报告的"手动配置步骤"创建 Render Staging 后端
2. 按照本报告的"环境变量配置"添加 Vercel Staging 和 Render Staging 的环境变量
3. 配置 Supabase Auth 的 Redirect URLs
4. 验证部署（健康检查、版本检查、前后端版本一致）
5. 执行公网 E2E 测试，重点验证 7 个用户最关注的问题
6. 全部通过后，将 staging 分支合并到 main

---

*报告生成时间: 2026-08-31*
*分支: staging/chat-core-2.0*
*最新 commit: 5e15e26*
*Vercel Staging URL: https://ai-persona-chat-lm2nlumr7-ai-persona-team.vercel.app*
