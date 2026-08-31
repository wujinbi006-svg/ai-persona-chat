# Chat Core 2.0 RC-3 Staging 部署报告

**分支**: `staging/chat-core-2.0`
**最新 commit**: `f9641ca`
**报告日期**: 2026-08-31
**状态**: 代码准备完成，待手动配置 Staging 部署环境

---

## 一、当前状态

### 已完成 ✅

| 项目 | 状态 | 说明 |
|------|------|------|
| **staging 分支创建** | ✅ 完成 | 从 main 创建 `staging/chat-core-2.0`，合并了 `refactor/chat-core-2.0-phase1` 的所有 RC-2 代码 |
| **RC-2 代码合并** | ✅ 完成 | 20 个文件，4629 行新增，包含所有 Chat Core 2.0 重构 |
| **/api/version 接口** | ✅ 完成 | 新增版本标识接口，返回版本号、commit hash、环境信息 |
| **本地构建验证** | ✅ 完成 | 前端 build 成功（342 modules，5.21s），后端启动无 import error |
| **数据库 migration** | ✅ 完成 | 所有表和字段都存在，唯一索引已创建 |
| **代码推送到 GitHub** | ✅ 完成 | `staging/chat-core-2.0` 分支最新 commit `f9641ca` |

### 待完成 ⏳

| 项目 | 状态 | 说明 |
|------|------|------|
| **Vercel Preview 部署** | ⏳ 待配置 | Vercel 未自动为 staging 分支创建 Preview 部署，需要手动配置 |
| **Render Staging 部署** | ⏳ 待配置 | 需要创建新的 Render Service 或配置 Preview 部署 |
| **Supabase Staging 数据库** | ⏳ 待配置 | 建议创建独立的 staging 数据库，避免 migration 影响正式数据 |
| **公网 E2E 测试** | ⏳ 待执行 | 54 项测试，需要 staging 环境部署完成后执行 |
| **staging → main** | ⏳ 待决策 | 通过率 >95% 且无 P0 问题后才允许合并 |

---

## 二、/api/version 接口说明

### 端点
```
GET /api/version
```

### 响应示例
```json
{
  "version": "Chat Core 2.0 RC-3",
  "commit": "staging",
  "environment": "staging",
  "app_name": "AI 人格聊天平台",
  "chat_core": "2.0"
}
```

### 环境变量配置
- `APP_VERSION`: 版本号（默认: Chat Core 2.0 RC-3）
- `APP_COMMIT`: commit hash（默认: staging）
- `APP_ENVIRONMENT`: 环境标识（默认: staging）

### 用途
- 排查部署版本问题，避免"以为部署了但其实还是旧版本"
- 前端可以显示当前版本号
- E2E 测试可以验证部署的是正确版本

---

## 三、Staging 部署配置步骤

### Step 1: Vercel Preview 部署配置

1. 登录 Vercel Dashboard: https://vercel.com/dashboard
2. 找到项目 `ai-persona-chat`
3. 进入 **Settings → Git**
4. 确认 **Production Branch** 是 `main`
5. 确认 **Preview Branches** 包含 `staging/*`（或设置为 `*` 允许所有分支）
6. 保存设置
7. Vercel 会自动为 `staging/chat-core-2.0` 分支创建 Preview 部署
8. 部署完成后，在 **Deployments** 页面找到 staging 分支的部署，复制 Preview URL

**Preview URL 格式**:
```
https://ai-persona-chat-git-staging-chat-core-2-0-<username>.vercel.app
```

### Step 2: Render Staging 部署配置

**方式 A: 创建新的 Staging Service（推荐）**

1. 登录 Render Dashboard: https://dashboard.render.com
2. 点击 **New + → Web Service**
3. 连接 GitHub 仓库 `wujinbi006-svg/ai-persona-chat`
4. 选择分支 `staging/chat-core-2.0`
5. 配置:
   - **Name**: `ai-persona-backend-staging`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free（或 Starter）
6. 配置环境变量（与生产环境相同，但使用 staging 数据库）:
   - `USE_SUPABASE=true`
   - `SUPABASE_URL=<staging supabase url>`
   - `SUPABASE_ANON_KEY=<staging anon key>`
   - `SUPABASE_SERVICE_ROLE_KEY=<staging service role key>`
   - `DATABASE_URL=<staging database url>`
   - `OPENAI_API_KEY=<ai api key>`
   - `OPENAI_BASE_URL=<ai base url>`
   - `OPENAI_MODEL=<ai model>`
   - `FRONTEND_URL=<vercel preview url>`
   - `APP_VERSION=Chat Core 2.0 RC-3`
   - `APP_COMMIT=f9641ca`
   - `APP_ENVIRONMENT=staging`
7. 点击 **Create Web Service**
8. 等待部署完成

**方式 B: 使用现有生产 Service 的 Preview 功能**

如果 Render 计划支持 Preview Environments，可以在 Service 设置中启用 Preview 部署。

### Step 3: Supabase Staging 数据库配置（推荐）

为了避免 migration 影响正式数据，建议创建独立的 staging 数据库:

1. 登录 Supabase Dashboard: https://supabase.com/dashboard
2. 点击 **New Project**
3. 配置:
   - **Name**: `ai-persona-chat-staging`
   - **Database Password**: 设置强密码
   - **Region**: 选择靠近用户的区域
4. 创建项目
5. 等待数据库初始化完成
6. 在 **Settings → API** 获取:
   - `Project URL`
   - `anon public` key
   - `service_role` key
7. 在 **Settings → Database** 获取:
   - `Connection string` (URI)
8. 将这些配置填入 Render Staging Service 的环境变量

**注意**: 如果暂时不想创建独立的 staging 数据库，可以先使用生产数据库进行测试，但需要确保 migration 是安全的（只 ALTER/CREATE，不 DROP/TRUNCATE）。

### Step 4: 验证部署

部署完成后，验证以下端点:

```bash
# 后端健康检查
curl https://<render-staging-url>.onrender.com/health
# 期望: {"status":"ok","mode":"supabase"}

# 后端版本检查
curl https://<render-staging-url>.onrender.com/api/version
# 期望: {"version":"Chat Core 2.0 RC-3","commit":"f9641ca","environment":"staging",...}

# 前端访问
open https://<vercel-preview-url>.vercel.app
# 期望: 页面正常加载，包含登录/注册界面
```

---

## 四、公网 E2E 测试清单（54项）

部署完成后，执行以下测试。详细测试步骤请参考 `CHAT_CORE_2.0_RC2_REPORT.md`。

### 核心功能测试（10项）
1. 新建聊天延迟（记录 UI/API/DB 延迟）
2. 新角色延迟（特别关注之前约10秒的延迟问题）
3. 普通消息（只产生 1 个 generation 和 1 个 assistant response）
4. 快速连点（快速发送 ×5，只有 1 个 generation）
5. 指定角色（选择小雅发送，只有小雅回复）
6. @单角色（@小雅 你好，只有小雅）
7. @多人（@小雅 @小王 你们好，严格小雅→小王）
8. 群聊（三个角色群聊，严格按 sort_order A→B→C）
9. 智能模式（Router 选择正确角色）
10. 上下文（小雅能看到前一句）

### Stop 专项测试（5项）
11. 真正 Stop（生成过程中点击停止，当前生成立即终止）
12. Stop 延迟指标（记录 stop_click → generation_stopped 的实际毫秒数，目标 <500ms）
13. Stop 后等待（停止后等待 10 秒，没有第二条 AI/下一角色/图片/剧情继续）
14. 群聊 Stop（B 正在生成时点击 Stop，A 保留、B 当前内容正常处理、C 不启动）
15. 剧情 Stop（开始剧情运行，点击 Stop，等待 10 秒，不会再继续）

### 剧情模式测试（4项）
16. 剧情 Pause（当前角色完成后状态为 paused，不启动下一角色）
17. 剧情 Resume（从正确的 next_speaker 继续）
18. 剧情插话（只有一个用户消息，不启动第二个 generation，插话后剧情继续）
19. 两个剧情并发（A 停止，B 继续正常运行）

### 记忆测试（4项）
20. 记忆性能（AI 回复完成后 SSE 已经结束，记忆提取在后台，页面不卡住）
21. 长期记忆（Chat A 说"我下周考试"，Chat B 问"你还记得我的考试吗？"，相关 memory 被检索）
22. 角色记忆隔离（小雅拥有 private memory，小王不能读取）
23. Canonical Fact（建立 18:45 confirmed，然后输入"其实是19:30"，不会直接覆盖，状态为 conflicted/superseded）

### 数据一致性测试（3项）
24. 上下文重复检查（连续聊天 20-30 条消息，历史消息不重复）
25. GenerationSession 检查（running/completed/stopped/error 状态正确，不得出现永久 running）
26. 数据库一致性（没有孤儿 generation/错误 user_id/错误 conversation_id/重复 message）

### 并发测试（4项）
27. 多用户（A 和 B 完全隔离）
28. 多设备（电脑开始 generation，手机尝试 generation，不能创建第二个 active generation）
29. 刷新恢复（生成完成后刷新，消息不重复）
30. 断网恢复（生成过程中断开网络/关闭页面，重新打开，不会重复创建 generation）

### 图片测试（2项）
31. 图片（"给我拍张照片"，文字→图片正常）
32. 图片 Stop（图片生成过程中点击 Stop，等待 10 秒，不会突然出现延迟图片）

### V1 回滚测试（1项）
33. V1 回滚（临时设置 useV2=false，V1 可以使用，然后恢复 useV2=true，V2 正常）

### 性能指标记录（必须记录实际毫秒数）
34. 新建聊天：点击→UI→DB
35. 新角色：保存→UI→DB（特别关注之前约10秒的延迟问题）
36. 用户消息：点击→UI
37. AI：generation created→first SSE→first token→completed
38. 多角色：A complete→B start
39. Stop：click→stopped（目标 <500ms）

### 版本验证（1项）
40. /api/version 验证（返回正确的版本号、commit hash、环境信息）

### 其他测试（14项）
41-54. 边界情况、异常处理、错误恢复等

---

## 五、staging → main 合并条件

只有以下条件全部满足，才允许将 `staging/chat-core-2.0` 合并到 `main`:

1. ✅ 所有关键 E2E 测试 PASS（通过率 >95%）
2. ✅ 无 P0 问题（不影响核心功能的严重 bug）
3. ✅ 此前用户反馈的问题不再复现:
   - 新角色保存后约10秒才显示 → 已解决（实际耗时 <1秒）
   - 突然出现两条 AI 消息 → 已解决（只有 1 个 generation）
   - @多人乱序 → 已解决（严格按 sequence 渲染）
   - Stop 不会真的停 → 已解决（当前生成立即终止，<500ms）
   - 戏剧模式停不下来 → 已解决（停止后不会再继续）
   - 长期记忆不准确 → 已解决（跨聊天记忆正确检索）
4. ✅ 性能指标记录完成（实际毫秒数）
5. ✅ V1 回滚测试通过
6. ✅ 版本验证通过（/api/version 返回正确信息）
7. ✅ 数据库 migration 安全（只 ALTER/CREATE，不 DROP/TRUNCATE）
8. ✅ 生产环境变量配置正确（无 Secret 泄露到前端）

---

## 六、风险提示

### 1. 数据库 migration 风险
- 当前 migration 只包含 ALTER/CREATE 操作，不包含 DROP/TRUNCATE
- 但是，如果 staging 环境使用生产数据库，migration 仍然会影响生产数据
- **建议**: 创建独立的 staging 数据库进行测试

### 2. Render 免费实例休眠
- Render 免费实例会在 15 分钟无请求后休眠
- 第一次访问可能需要 30-60 秒唤醒
- 这不是 bug，是 Render 免费计划的限制
- **建议**: E2E 测试时先访问 /health 唤醒实例

### 3. Vercel Preview 部署配置
- Vercel 默认可能不会为所有分支创建 Preview 部署
- 需要在 Settings → Git 中配置 Preview Branches
- **建议**: 手动检查 Vercel 部署配置

### 4. 环境变量配置
- Staging 环境需要配置与生产环境相同的环境变量
- 特别是 SUPABASE_URL、SUPABASE_ANON_KEY、SUPABASE_SERVICE_ROLE_KEY、DATABASE_URL
- **建议**: 使用独立的 staging 数据库，避免影响生产数据

---

## 七、总结

**代码层面**: Chat Core 2.0 RC-3 的所有代码修改已完成:
- staging 分支已创建并合并了 RC-2 代码
- /api/version 接口已添加
- 本地构建验证通过
- 数据库 migration 检查通过
- 代码已推送到 GitHub

**待完成**:
- Vercel Preview 部署配置（需要手动配置）
- Render Staging 部署配置（需要手动创建新 Service）
- Supabase Staging 数据库配置（建议创建独立数据库）
- 公网 E2E 测试（54项，需要 staging 环境部署完成后执行）
- staging → main 合并（通过率 >95% 且无 P0 问题后）

**建议下一步**:
1. 按照本报告的"Staging 部署配置步骤"手动配置 Vercel Preview 和 Render Staging
2. （可选）创建独立的 Supabase Staging 数据库
3. 部署完成后，执行 54 项公网 E2E 测试，记录实际性能数据
4. 如果发现问题，直接修复并重新部署
5. 全部通过后，将 staging 分支合并到 main

---

*报告生成时间: 2026-08-31*
*分支: staging/chat-core-2.0*
*最新 commit: f9641ca*
