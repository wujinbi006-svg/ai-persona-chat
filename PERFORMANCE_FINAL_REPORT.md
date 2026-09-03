# Performance Final Report（2026-09-03）

## 已验证

- 本地 warm 普通聊天 10/10：TTFT P50 1104ms，P95 1201ms，Max 1239ms；Full P50 1834ms，P95 2020ms。
- 本地 cold 首请求：TTFT 3679ms；LLM connection 2977ms；LLM TTFT 3517ms。
- 每次请求均为 1 次 LLM 调用。
- A/B 实验两组各 10 次真实请求，全部成功：
  - New Client：connection P50 375ms，P95 1906ms；TTFT P50 738ms，P95 2419ms；Full P50 1071ms，P95 2771ms。
  - Shared Client：connection P50 375ms，P95 421ms；TTFT P50 711ms，P95 896ms；Full P50 1068ms，P95 1239ms。
- 共享 Client 的 connection P50 几乎无改善，但 P95 从 1906ms 降至 421ms；TTFT P95 从 2419ms 降至 896ms；Full P95 从 2771ms 降至 1239ms。该结果说明尾延迟稳定性改善明显，但不是每次请求都节省固定连接时间。
- 生产 `/health` 连续请求成功，约 340–500ms。

## 未验证

- 当前生产部署的聊天 trace：`/api/version` 返回 `commit=unknown`，无法证明包含当前性能分支。
- 生产聊天 10 次 cold/warm、浏览器 E2E、Vercel→Render→LLM 分段 trace：未完成。
- 单独 TCP socket 复用：未直接观测，仅能确认 SDK transport pooling 架构存在。

## 代码变更

- 修复 benchmark 完整读取 `trace_data`。
- 将共享 LLM Client 接入 FastAPI shutdown 生命周期。
- 删除未使用 import。
- 新增独立 A/B benchmark 脚本与结果文件。

## 测试

- `pytest`：8 passed
- `git diff --check`：通过
- 前端构建：成功

## 结论

PRIMARY BOTTLENECK = 外部 LLM 首 token 延迟及冷启动高尾
SECONDARY BOTTLENECK = 生产基础设施冷启动/网络波动
Memory、DB、ResponsePlan 不是当前瓶颈。

当前不应继续修改 Chat Core 业务逻辑；下一步应先让生产部署带 trace 的版本可识别，再进行真实生产聊天归因。
