"""
Chat Core 2.0 - Performance Baseline Test Script

性能基准测试脚本：直接调用后端 API，收集 SSE 事件和 trace_data，
输出各场景的 P50/P90/P95/Max 统计。

用法：
  python perf_baseline.py [--backend URL] [--scenarios all|normal|mention_single|mention_double|group|drama] [--runs N]

默认后端：http://127.0.0.1:8000
"""
import argparse
import json
import time
import statistics
import sys
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

# 添加 backend 目录到 path，便于导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx


# ============================================================
# 数据结构
# ============================================================

@dataclass
class TestResult:
    """单次测试结果。"""
    scenario: str
    success: bool
    error: Optional[str] = None
    # 前端视角计时（模拟）
    t0: float = 0.0  # 请求发出
    t14: float = 0.0  # 首个 SSE 事件到达
    t15: float = 0.0  # 首个 content token 到达
    t16: float = 0.0  # 完整回复结束
    # 后端 trace 数据
    backend_trace: Optional[Dict[str, Any]] = None
    # 元数据
    llm_request_count: int = 0
    speaker_count: int = 0
    cold_start: bool = False

    @property
    def ttft_ms(self) -> float:
        """Time To First Token（请求发出→首个 content token）"""
        if self.t15 and self.t0:
            return (self.t15 - self.t0) * 1000
        return 0.0

    @property
    def full_response_ms(self) -> float:
        """完整响应时间（请求发出→完成）"""
        if self.t16 and self.t0:
            return (self.t16 - self.t0) * 1000
        return 0.0

    @property
    def sse_latency_ms(self) -> float:
        """请求发出→首个 SSE 事件"""
        if self.t14 and self.t0:
            return (self.t14 - self.t0) * 1000
        return 0.0


@dataclass
class ScenarioStats:
    """场景统计结果。"""
    scenario: str
    results: List[TestResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def ttft_values(self) -> List[float]:
        return [r.ttft_ms for r in self.results if r.success and r.ttft_ms > 0]

    @property
    def full_response_values(self) -> List[float]:
        return [r.full_response_ms for r in self.results if r.success and r.full_response_ms > 0]

    def percentile(self, values: List[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_vals) else f
        return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

    def summary(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "total_runs": len(self.results),
            "success_runs": self.success_count,
            "failure_runs": len(self.results) - self.success_count,
            "ttft_ms": {
                "p50": round(self.percentile(self.ttft_values, 50), 1),
                "p90": round(self.percentile(self.ttft_values, 90), 1),
                "p95": round(self.percentile(self.ttft_values, 95), 1),
                "max": round(max(self.ttft_values), 1) if self.ttft_values else 0,
                "mean": round(statistics.mean(self.ttft_values), 1) if self.ttft_values else 0,
            },
            "full_response_ms": {
                "p50": round(self.percentile(self.full_response_values, 50), 1),
                "p90": round(self.percentile(self.full_response_values, 90), 1),
                "p95": round(self.percentile(self.full_response_values, 95), 1),
                "max": round(max(self.full_response_values), 1) if self.full_response_values else 0,
                "mean": round(statistics.mean(self.full_response_values), 1) if self.full_response_values else 0,
            },
        }


# ============================================================
# 测试执行
# ============================================================

class PerfTester:
    """性能测试执行器。"""

    def __init__(self, backend_url: str, timeout: int = 180):
        self.backend_url = backend_url.rstrip("/")
        self.timeout = timeout
        # trust_env=False 避免使用系统代理导致 502
        self.client = httpx.Client(timeout=timeout, trust_env=False)

    def close(self):
        self.client.close()

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头（本地模式不需要 auth）。"""
        return {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

    def run_chat_test(
        self,
        scenario: str,
        conversation_id: int,
        message: str,
        mode: str = "normal",
        strategy: str = "specific",
        character_id: Optional[int] = None,
        mentioned_character_ids: Optional[List[int]] = None,
    ) -> TestResult:
        """执行单次聊天测试。"""
        result = TestResult(scenario=scenario, success=False)
        url = f"{self.backend_url}/api/chat/v2/generate"

        payload = {
            "conversation_id": conversation_id,
            "message": message,
            "mode": mode,
            "strategy": strategy,
        }
        if character_id:
            payload["character_id"] = character_id
        if mentioned_character_ids:
            payload["mentioned_character_ids"] = mentioned_character_ids

        # T0: 请求发出
        result.t0 = time.perf_counter()

        try:
            with self.client.stream("POST", url, json=payload, headers=self._get_headers()) as response:
                response.raise_for_status()

                first_sse = False
                first_token = False
                completed_event = False

                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type", "")

                        # T14: 首个 SSE 事件
                        if not first_sse:
                            first_sse = True
                            result.t14 = time.perf_counter()

                        # T15: 首个 content token
                        if event_type == "content" and not first_token:
                            first_token = True
                            result.t15 = time.perf_counter()

                        # trace_data 事件
                        if event_type == "trace_data":
                            result.backend_trace = event.get("trace", {})
                            result.llm_request_count = event.get("trace", {}).get("llm_request_count", 0)
                            result.cold_start = event.get("trace", {}).get("cold_start", False)
                            # trace_data is emitted after generation_completed; keep
                            # reading through this event so the run is auditable.
                            if completed_event:
                                break

                        # 记录 speaker 数量
                        if event_type == "generation_started":
                            result.speaker_count = len(event.get("speakers", []))

                        # 完成事件
                        if event_type in ("generation_completed", "generation_stopped", "generation_error", "generation_conflict"):
                            if event_type == "generation_completed":
                                result.success = True
                                completed_event = True
                            elif event_type in ("generation_error", "generation_conflict"):
                                result.error = event.get("message", event_type)
                                break

                # T16: 流结束
                result.t16 = time.perf_counter()

                # 如果没有收到完成事件但流正常结束，也算成功
                if not result.success and result.t15 > 0:
                    result.success = True

        except Exception as e:
            result.error = str(e)[:200]
            result.t16 = time.perf_counter()

        return result

    def warmup(self, conversation_id: int, character_id: int):
        """预热请求（避免冷启动影响测试）。"""
        print("  [Warmup] 发送预热请求...")
        result = self.run_chat_test(
            scenario="warmup",
            conversation_id=conversation_id,
            message="你好，请用一句话回复。",
            character_id=character_id,
        )
        print(f"  [Warmup] 完成: TTFT={result.ttft_ms:.0f}ms, Full={result.full_response_ms:.0f}ms, cold_start={result.cold_start}")
        return result


# ============================================================
# 场景定义
# ============================================================

SCENARIOS = {
    "normal": {
        "name": "普通聊天",
        "mode": "normal",
        "strategy": "specific",
        "messages": [
            "你好，请介绍一下你自己。",
            "今天天气怎么样？",
            "你喜欢什么颜色？",
            "讲一个简短的笑话。",
            "你最喜欢的食物是什么？",
            "描述一下你的性格。",
            "你有什么爱好？",
            "说一句鼓励的话。",
            "你平时喜欢做什么？",
            "用三句话介绍你的世界观。",
        ],
    },
    "mention_single": {
        "name": "@单角色",
        "mode": "normal",
        "strategy": "mention",
        "messages": [
            "@角色A 你好",
            "@角色A 今天怎么样？",
            "@角色A 你在做什么？",
            "@角色A 喜欢什么音乐？",
            "@角色A 你的梦想是什么？",
            "@角色A 最近看了什么书？",
            "@角色A 推荐一部电影",
            "@角色A 你最擅长什么？",
            "@角色A 说一句名言",
            "@角色A 你觉得幸福是什么？",
        ],
    },
    "mention_double": {
        "name": "@双角色",
        "mode": "normal",
        "strategy": "mention",
        "messages": [
            "@角色A @角色B 你们好",
            "@角色A @角色B 讨论一下科技",
            "@角色A @角色B 谁更聪明？",
            "@角色A @角色B 你们的关系如何？",
            "@角色A @角色B 一起做个决定",
            "@角色A @角色B 辩论一下人工智能",
            "@角色A @角色B 推荐旅行目的地",
            "@角色A @角色B 聊聊未来",
            "@角色A @角色B 你们的共同点是什么？",
            "@角色A @角色B 给我一些建议",
        ],
    },
    "group": {
        "name": "群聊",
        "mode": "group",
        "strategy": "specific",
        "messages": [
            "大家好，我们来聊聊天",
            "讨论一下最近的热点",
            "每个人说一句开场白",
            "你们觉得什么是成功？",
            "分享一个有趣的故事",
            "讨论一下人生意义",
            "如果可以穿越，你们想去哪？",
            "描述一下理想的一天",
            "你们最害怕什么？",
            "给年轻人一些忠告",
        ],
    },
    "drama": {
        "name": "剧情",
        "mode": "drama",
        "strategy": "specific",
        "messages": [
            "场景：咖啡馆，两个老朋友偶遇",
            "场景：深夜的办公室，加班的同事",
            "场景：火车站台，离别时刻",
            "场景：山顶看日出，两人对话",
            "场景：雨天的书店，陌生人相遇",
            "场景：大学宿舍，毕业前夜",
            "场景：医院走廊，等待消息",
            "场景：机场安检，最后一面",
            "场景：公园长椅，回忆往事",
            "场景：新年倒计时，跨年时刻",
        ],
    },
}


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Chat Core 2.0 Performance Baseline Test")
    parser.add_argument("--backend", default="http://127.0.0.1:8000", help="后端 URL")
    parser.add_argument("--conversation-id", type=int, default=1, help="测试会话 ID")
    parser.add_argument("--character-id", type=int, default=1, help="测试角色 ID（specific 模式）")
    parser.add_argument("--character-ids", type=int, nargs="+", default=[1, 2], help="@多人/群聊角色 ID 列表")
    parser.add_argument("--scenarios", nargs="+", default=["all"],
                        choices=["all", "normal", "mention_single", "mention_double", "group", "drama"],
                        help="测试场景")
    parser.add_argument("--runs", type=int, default=10, help="每个场景运行次数")
    parser.add_argument("--no-warmup", action="store_true", help="跳过预热")
    parser.add_argument("--output", default="perf_baseline_results.json", help="结果输出文件")
    args = parser.parse_args()

    print("=" * 70)
    print("Chat Core 2.0 - Performance Baseline Test")
    print("=" * 70)
    print(f"Backend: {args.backend}")
    print(f"Conversation ID: {args.conversation_id}")
    print(f"Character ID: {args.character_id}")
    print(f"Character IDs: {args.character_ids}")
    print(f"Scenarios: {args.scenarios}")
    print(f"Runs per scenario: {args.runs}")
    print("=" * 70)

    tester = PerfTester(args.backend)

    try:
        # 预热
        if not args.no_warmup:
            tester.warmup(args.conversation_id, args.character_id)
            print()

        # 确定要测试的场景
        if "all" in args.scenarios:
            scenario_names = list(SCENARIOS.keys())
        else:
            scenario_names = args.scenarios

        all_stats = {}

        for scenario_name in scenario_names:
            scenario = SCENARIOS[scenario_name]
            print(f"\n{'='*70}")
            print(f"场景: {scenario['name']} ({scenario_name})")
            print(f"模式: {scenario['mode']}, 策略: {scenario['strategy']}")
            print(f"{'='*70}")

            stats = ScenarioStats(scenario=scenario_name)

            for i in range(args.runs):
                message = scenario["messages"][i % len(scenario["messages"])]

                # 根据场景设置参数
                kwargs = dict(
                    scenario=scenario_name,
                    conversation_id=args.conversation_id,
                    message=message,
                    mode=scenario["mode"],
                    strategy=scenario["strategy"],
                )

                if scenario["strategy"] == "specific":
                    kwargs["character_id"] = args.character_id
                elif scenario["strategy"] == "mention":
                    if scenario_name == "mention_single":
                        kwargs["mentioned_character_ids"] = [args.character_ids[0]]
                        # 替换消息中的角色名
                        message = message.replace("@角色A", f"@角色{args.character_ids[0]}")
                        kwargs["message"] = message
                    elif scenario_name == "mention_double":
                        kwargs["mentioned_character_ids"] = args.character_ids[:2]
                        message = message.replace("@角色A", f"@角色{args.character_ids[0]}").replace("@角色B", f"@角色{args.character_ids[1]}")
                        kwargs["message"] = message

                print(f"  [{i+1}/{args.runs}] 发送: {message[:40]}...", end=" ", flush=True)

                result = tester.run_chat_test(**kwargs)
                stats.results.append(result)

                if result.success:
                    print(f"OK - TTFT={result.ttft_ms:.0f}ms, Full={result.full_response_ms:.0f}ms, LLM_reqs={result.llm_request_count}")
                else:
                    print(f"FAIL - {result.error}")

                # 场景间短暂休息
                if i < args.runs - 1:
                    time.sleep(1)

            # 输出统计
            summary = stats.summary()
            all_stats[scenario_name] = summary
            print(f"\n  --- {scenario['name']} 统计 ---")
            print(f"  成功率: {summary['success_runs']}/{summary['total_runs']}")
            print(f"  TTFT (ms):  P50={summary['ttft_ms']['p50']}, P90={summary['ttft_ms']['p90']}, P95={summary['ttft_ms']['p95']}, Max={summary['ttft_ms']['max']}, Mean={summary['ttft_ms']['mean']}")
            print(f"  Full (ms):  P50={summary['full_response_ms']['p50']}, P90={summary['full_response_ms']['p90']}, P95={summary['full_response_ms']['p95']}, Max={summary['full_response_ms']['max']}, Mean={summary['full_response_ms']['mean']}")

            # 输出后端 trace 详情（取第一个成功结果）
            successful_traces = [r for r in stats.results if r.success and r.backend_trace]
            if successful_traces:
                trace = successful_traces[0].backend_trace
                durations = trace.get("durations", {})
                print(f"\n  --- 后端 Trace 详情（首次成功请求）---")
                print(f"  Auth: {durations.get('auth_ms', 'N/A')}ms")
                print(f"  DB Query: {durations.get('db_query_ms', 'N/A')}ms")
                print(f"  Memory: {durations.get('memory_retrieval_ms', 'N/A')}ms")
                print(f"  ResponsePlan: {durations.get('response_plan_ms', 'N/A')}ms")
                print(f"  LLM Connection: {durations.get('llm_connection_ms', 'N/A')}ms")
                print(f"  LLM TTFT: {durations.get('llm_ttft_ms', 'N/A')}ms")
                print(f"  LLM Generation: {durations.get('llm_generation_ms', 'N/A')}ms")
                print(f"  Total Backend: {durations.get('total_backend_ms', 'N/A')}ms")
                print(f"  LLM Request Count: {trace.get('llm_request_count', 'N/A')}")
                print(f"  Cold Start: {trace.get('cold_start', 'N/A')}")

                # 逐角色 trace
                speaker_traces = trace.get("speaker_traces", [])
                if speaker_traces:
                    print(f"\n  --- 逐角色 Trace ---")
                    for st in speaker_traces:
                        print(f"    {st.get('character_name', '?')} (idx={st.get('speaker_index')}): "
                              f"TTFT={st.get('ttft_ms', 'N/A')}ms, "
                              f"Duration={st.get('generation_duration_ms', 'N/A')}ms, "
                              f"Tokens={st.get('token_count', 'N/A')}")

        # 保存结果
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_stats, f, ensure_ascii=False, indent=2)
        print(f"\n{'='*70}")
        print(f"结果已保存到: {output_path}")
        print(f"{'='*70}")

    finally:
        tester.close()


if __name__ == "__main__":
    main()
