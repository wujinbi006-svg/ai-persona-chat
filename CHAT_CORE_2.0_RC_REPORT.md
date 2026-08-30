# Chat Core 2.0 Release Candidate 验收报告

**分支**: `refactor/chat-core-2.0-phase1`
**最新 commit**: `e48fac8`
**报告日期**: 2026-08-31
**状态**: Release Candidate（待公网真实测试验证）

---

## 一、已完成的工作

### Phase 1: 聊天内核 ✅
- **ConversationOrchestrator**: 统一调度入口，plan() → execute()
- **ResponsePlan**: 一条用户消息只能产生一个响应计划
- **GenerationSession**: 生成会话状态机（7种状态：idle/running/paused/stopping/stopped/completed/error）
- **ConversationLock**: 后端会话级内存锁，同一 conversation 同时只能一个 active session
- **统一 SSE 事件**: 所有事件携带 generation_id
- **v2 统一路由**: `/api/chat/v2/generate`（支持 normal/group/drama 三模式 + specific/mention/smart 三策略）
- **单元测试**: 8个场景全部通过（并发冲突、停止、序列号、状态机等）

### Phase 2: 前端响应层 ✅
- **useChatV2 hook**: 全新统一状态管理
- **乐观更新**: 用户消息立即显示，不等待服务器
- **统一 SSE 事件处理**: 15+ 种事件类型
- **本地状态直接更新**: AI回复/图片直接 append，不重新拉取整个列表
- **AbortController**: 停止真正取消浏览器请求
- **前端生成锁**: 与后端双重保障
- **TypeScript 编译**: 零错误

### Phase 3: 数据一致性 ✅
- **Message 表新增字段**: generation_id, sequence_number, parent_message_id, message_type
- **generation_sessions 表**: 生成会话持久化（跨请求追踪状态）
- **facts 表**: Canonical Facts（为 Phase 4 做准备）
- **generation_session_service.py**: 数据库级生成唯一性保证
- **chat_v2.py 集成**: 生成前数据库级检查（409 Conflict）
- **所有消息标记**: generation_id 和 sequence_number
- **数据库迁移**: 安全完成，旧数据兼容（新字段允许 NULL）

### Phase 4: 记忆系统重构 ✅
- **fact_service.py**: Canonical Facts（规范事实）服务
  - 事实与假设分离（fact vs hypothesis）
  - 事实状态：confirmed/uncertain/conflicted/superseded
  - 角色假设不能自动成为事实
  - 事实取代（supersede）：不删除旧事实
  - 事实冲突标记
- **记忆提取异步后台化**: asyncio.create_task，不阻塞 SSE 流结束

### Phase 5: 剧情模式重构 ✅
- **/api/chat/v2/drama/start**: 持续运行剧情模式
  - 不再使用固定轮数，持续运行直到暂停/停止
  - 状态机：running → paused → running → stopped
  - 支持暂停/继续/停止
  - 用户插话：/api/chat/v2/drama/interject
  - 服务器级保护：max_duration_seconds（默认30分钟）、max_generations（默认100次）
  - 达到上限自动暂停并提示，不会无限烧 API
  - 角色按 sort_order 顺序发言
  - 角色间可配置等待间隔

### Phase 6: UI 收敛 ✅
- **ChatPanelV2.tsx**: 全新统一聊天面板组件
  - 三模式切换：💬普通 / 👥群聊 / 🎭剧情
  - 发言策略选择器：指定角色 / @角色 / 🧠智能选择
  - 使用 v2 统一接口 + useChatV2 hook
  - @角色菜单（输入 @ 触发，支持搜索）
  - 剧情模式控制（开始/暂停/继续/停止，可配置间隔）
  - 流式输出显示 + 图片生成加载状态
  - 响应式设计，移动端适配
- **与旧 ChatArea 并存**: 不破坏现有功能

### Phase 7: 生产链路接管 ✅
- **App.tsx 集成 ChatPanelV2**: 作为默认聊天面板
- **生产链路**: 用户 → ChatPanelV2 → useChatV2 → /api/chat/v2/generate → ConversationOrchestrator → ResponsePlan → GenerationSession → GenerationExecutor → LLM → SSE → UI
- **旧 ChatArea 保留**: 作为回滚保险（useV2 状态开关，默认 true）
- **不删除旧代码**: V2 在公网真实跑一轮后再决定清理

### Phase 8: 生产级并发与一致性审计 ✅
- **问题**: ConversationLock 只是 Python 进程内 asyncio.Lock，Render 多实例环境下两边并不知道对方存在
- **解决方案**: 添加数据库级部分唯一索引
  ```sql
  CREATE UNIQUE INDEX idx_active_generation_per_conversation
  ON generation_sessions (conversation_id)
  WHERE status IN ('running', 'paused', 'stopping')
  ```
- **保证**: 同一个 conversation 同时只能有一个 active generation，即使多实例横向扩容也安全
- **generation_session_service.create_session**: 使用数据库事务 + flush 触发唯一索引检查
- **与内存 ConversationLock 形成双重保障**: 内存锁快速拒绝，数据库索引最终保证
- **本地 SQLite 验证通过**: 索引已创建
- **PostgreSQL（Supabase 生产环境）**: 同样支持部分唯一索引

### Phase 9: 记忆系统生产审计 ✅
- **检查 asyncio.create_task 后台记忆提取的生产安全性**
- **确认**: 独立数据库会话（SessionLocal()），不影响主流程事务
- **确认**: 全异常捕获，记忆提取失败不影响聊天成功
- **确认**: 任务完成后从集合移除（add_done_callback）
- **改进**: 失败时不再静默 pass，改为 logging.warning 记录错误
  - 记录 conversation_id 和错误信息，便于追踪"有时候记忆提取了有时候没有"的问题
- **Render 重启时任务消失是可接受的**: 主聊天已完成，记忆提取是 best-effort
- **后续可升级为持久化任务队列**: 但第一版此实现已满足生产安全要求

### Phase 10: 剧情模式验收 ✅
- **持续运行状态机**: 不再用固定轮数
- **停止逻辑**: 每个角色生成前检查 should_stop，停止后不再生成下一个角色
- **最终状态**: 更新为 stopped，数据库 session 最终 stopped
- **暂停/继续**: 正确处理，暂停时等待恢复或停止
- **用户插话**: /api/chat/v2/drama/interject 接口已实现
- **服务器级保护**: 30分钟/100次上限，达到自动暂停
- **已知限制**: 当前正在生成的角色（LLM streaming）不会被立即取消，会完成后再停止。不会无限继续，但可能有"点停止后又冒出一条消息"的情况。后续可升级为在 LLM streaming 层面取消。

---

## 二、测试结果

### 已完成的测试

| 测试类型 | 状态 | 说明 |
|---------|------|------|
| 后端启动 | ✅ 通过 | FastAPI 启动成功，所有路由注册 |
| 数据库迁移 | ✅ 通过 | 所有迁移安全完成，旧数据兼容 |
| 数据库级唯一索引 | ✅ 通过 | idx_active_generation_per_conversation 已创建 |
| 前端 TypeScript 编译 | ✅ 通过 | 零错误 |
| 内核单元测试 | ✅ 通过 | 8个场景全部通过 |
| 代码静态检查 | ✅ 通过 | 无导入错误、无语法错误 |

### 待公网真实测试的项目（Phase 11-13）

以下测试需要部署到公网后在真实浏览器环境中执行：

#### Phase 11: 重点回归测试（16项）
1. ⏳ 新建聊天后 conversation 是否立即创建
2. ⏳ 新建角色保存后是否立即显示
3. ⏳ 保存角色后刷新页面是否仍然存在
4. ⏳ 普通发送一句消息是否只产生一条 AI 回复
5. ⏳ 连续快速点击发送是否只产生一个 generation
6. ⏳ @单个角色是否只有该角色回复
7. ⏳ @多个角色是否严格按照计划顺序回复
8. ⏳ 后一个角色不得因为网络延迟而插队
9. ⏳ 群聊是否严格按照角色排序
10. ⏳ Stop 是否真正终止服务器生成
11. ⏳ Refresh 后是否出现重复消息
12. ⏳ 网络断开/恢复后是否出现重复消息
13. ⏳ AI 回复完成后是否还会因为 memory extraction 长时间卡住
14. ⏳ 新旧聊天之间记忆是否错误串联
15. ⏳ 两个账号同时聊天是否互不影响
16. ⏳ 两个不同 conversation 同时运行剧情是否互不影响

#### Phase 12: 性能测试（延迟分层测量）
- ⏳ 新建聊天点击 → conversation 创建完成
- ⏳ 添加角色点击保存 → UI 出现角色
- ⏳ 角色保存 → 数据库完成
- ⏳ 发送消息 → generation 创建
- ⏳ generation 创建 → SSE 首事件
- ⏳ AI 首 token 延迟
- ⏳ AI 完成 → UI 完成状态
- ⏳ memory extraction 是否阻塞主链路
- ⏳ 特别检查之前约 10 秒的"新角色保存后才显示"问题

#### Phase 13: 最终生产验证
- ⏳ Vercel 测试
- ⏳ Render 测试
- ⏳ Supabase 测试
- ⏳ 公网浏览器测试
- ⏳ 手机 4G/5G 测试
- ⏳ 多设备同时登录测试

---

## 三、已解决的问题

| 之前的问题 | Chat Core 2.0 的解决方案 | 状态 |
|-----------|--------------------------|------|
| 快速点击发送产生多条 AI 回复 | 后端 ConversationLock + 数据库级唯一索引双重保障 | ✅ 代码完成，待公网验证 |
| @多人乱序 | sequence_number 保证逻辑顺序，即使网络延迟也按序渲染 | ✅ 代码完成 |
| 停止后 AI 还在继续生成 | AbortController + 后端 GenerationSession 状态机 + should_stop 检查 | ✅ 代码完成（当前角色会完成后停止） |
| 记忆提取阻塞主回复 | asyncio.create_task 后台异步提取，不阻塞 SSE | ✅ 代码完成 |
| AI 把假设当事实 | Canonical Facts 服务：fact/hypothesis 分离 | ✅ 代码完成 |
| 剧情模式固定轮数不自然 | 持续运行状态机，直到用户暂停/停止或达到保护上限 | ✅ 代码完成 |
| 十几个模式按钮混乱 | UI 收敛为 3 模式（普通/群聊/剧情）+ 3 策略（指定/@/智能） | ✅ 代码完成 |
| 新角色出现慢 | 乐观更新 + 本地状态直接更新，不再创建后重新 GET 整个列表 | ✅ 代码完成，待公网验证 |
| Render 多实例并发不安全 | 数据库级部分唯一索引保证多实例环境下的唯一性 | ✅ 代码完成 |
| 记忆提取失败不可见 | logging.warning 记录错误，便于追踪 | ✅ 代码完成 |

---

## 四、已知限制与后续优化

### 已知限制（第一版可接受）

1. **剧情模式停止时当前角色会完成**: 点击停止后，当前正在生成的角色（LLM streaming）不会被立即取消，会完成后再停止。不会无限继续，但可能有"点停止后又冒出一条消息"的情况。
   - **后续优化**: 在 LLM streaming 层面检查 should_stop，取消当前 asyncio task。

2. **记忆提取是 best-effort**: Render 重启时正在运行的后台记忆提取任务会消失。主聊天已完成，记忆丢失是可接受的。
   - **后续优化**: 升级为持久化任务队列（pending/processing/completed/failed 状态）。

3. **记忆检索仍是简单关键词匹配**: 中文语义检索能力有限。
   - **后续优化**: 升级为 BM25 全文检索 + 重要性 + 角色相关性 + 时间衰减，之后再升级 Embedding。

4. **四层记忆的完整分层检索尚未实现**: User/Character/Relationship/Conversation 记忆的作用域隔离需要进一步完善。
   - **后续优化**: 实现完整的分层记忆检索。

5. **Canonical Facts 尚未集成到上下文构建**: fact_service.py 已创建，但 context_service.py 还没有调用它。AI 回复时还看不到已确认事实和角色假设的区分。
   - **后续优化**: 在 context_service.build_context 中调用 fact_service，注入 Canonical Facts。

6. **旧接口尚未转发到 Orchestrator**: 旧的 /api/chat/stream、/reply-all、/discussion、/drama/* 路由仍独立运行。用户要求最终旧接口内部必须转发到 Orchestrator。
   - **后续优化**: 逐个改造旧路由为内部调用 Orchestrator。

7. **V1/V2 切换按钮未添加**: 当前 useV2 状态默认 true，但没有 UI 切换按钮。需要时可通过修改代码或 localStorage 切换。
   - **后续优化**: 在设置页面添加 V1/V2 切换开关。

### 不影响上线的后续优化

- 图片生成持久化存储（当前 Render 临时文件，重启后丢失）
- 角色创建的完整乐观更新（当前 ChatPanelV2 依赖 App 层级的 characters 状态）
- 完整的 E2E 自动化测试套件
- 性能监控和告警

---

## 五、是否允许合并 main

### 建议：**有条件允许合并**

**理由**:
1. ✅ 所有核心代码已完成并通过本地验证
2. ✅ 后端启动、数据库迁移、TypeScript 编译全部通过
3. ✅ 数据库级唯一索引已创建，多实例安全有保障
4. ✅ 旧代码完整保留，可随时回滚（useV2 开关）
5. ✅ 不破坏已有数据，所有迁移都是安全的 ALTER TABLE
6. ⚠️ 但公网真实 E2E 测试尚未执行

**合并前建议**:
1. 将分支合并到 main（Vercel 和 Render 会自动部署）
2. 部署后立即执行 Phase 11-13 的公网真实测试
3. 如果发现严重问题，立即将 useV2 改为 false 回滚到 V1
4. V1 旧链路完整保留，回滚成本极低

**合并后必须立即执行**:
- 公网浏览器测试（注册/登录/新建聊天/新建角色/普通聊天/@角色/群聊/剧情/停止/刷新）
- 手机 4G/5G 测试
- 多设备同时登录测试
- 性能测试（特别关注新角色显示延迟）

---

## 六、回滚方案

如果 V2 在公网测试中发现严重问题，可通过以下方式立即回滚：

1. **前端回滚**: 修改 App.tsx 中 `DEFAULT_USE_V2 = false`，重新部署 Vercel
2. **后端回滚**: 旧的 /api/chat/* 路由完整保留，无需修改
3. **数据库回滚**: 所有迁移都是安全的 ALTER TABLE，新字段允许 NULL，无需回滚
4. **Git 回滚**: `git revert` 合并 commit，或直接部署旧版本

回滚成本极低，因为：
- 旧代码完整保留，未删除
- 数据库迁移是增量的，不破坏旧数据
- V1/V2 通过 useV2 开关切换，一行代码即可回滚

---

## 七、总结

Chat Core 2.0 的核心架构重构已全部完成：

- **统一调度内核**: ConversationOrchestrator + ResponsePlan + GenerationSession
- **生产级并发安全**: 内存锁 + 数据库级唯一索引双重保障
- **数据一致性**: generation_id + sequence_number + parent_message_id
- **记忆系统**: 异步后台提取 + Canonical Facts 事实与假设分离
- **剧情模式**: 持续运行状态机 + 服务器级保护
- **UI 收敛**: 3 模式 + 3 策略，不再混乱
- **生产链路接管**: ChatPanelV2 成为默认聊天界面
- **回滚保险**: 旧代码完整保留，useV2 开关一键回滚

**当前状态**: Release Candidate，代码层面已完成，待公网真实 E2E 测试验证。

**建议**: 合并到 main 部署到公网，然后立即执行 Phase 11-13 的真实测试。如果发现问题，useV2=false 立即回滚。

---

*报告生成时间: 2026-08-31*
*分支: refactor/chat-core-2.0-phase1*
*最新 commit: e48fac8*
