"""
Chat Core 2.0 Phase 1 - 单元测试
测试：ResponsePlan、GenerationSession、ConversationLock、ConversationOrchestrator
"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.services.orchestrator import (
    ConversationOrchestrator, ChatMode, SpeakerStrategy,
    GenerationStatus, ResponsePlan, GenerationSession,
    ConversationLock, GenerationConflictError, get_orchestrator,
)


# 模拟角色对象
class MockCharacter:
    def __init__(self, id, name):
        self.id = id
        self.name = name


def test_response_plan():
    """测试 ResponsePlan 创建"""
    print("=== 测试 ResponsePlan ===")
    plan = ResponsePlan(
        mode=ChatMode.NORMAL,
        speakers=[1, 2],
        strategy=SpeakerStrategy.MENTION,
        user_message="@小雅 @小王 你好",
        conversation_id=1,
        user_id="user1",
    )
    assert plan.mode == ChatMode.NORMAL
    assert plan.speakers == [1, 2]
    assert plan.strategy == SpeakerStrategy.MENTION
    assert plan.generation_id.startswith("gen_")
    print("  ✅ ResponsePlan 创建成功")
    print(f"  generation_id: {plan.generation_id}")


def test_generation_session_state_machine():
    """测试 GenerationSession 状态机"""
    print("\n=== 测试 GenerationSession 状态机 ===")
    plan = ResponsePlan(mode=ChatMode.NORMAL, speakers=[1], conversation_id=1, user_id="u1")
    session = GenerationSession(
        generation_id=plan.generation_id,
        conversation_id=1,
        user_id="u1",
        plan=plan,
    )

    assert session.status == GenerationStatus.IDLE
    assert not session.is_active
    print("  ✅ 初始状态 IDLE")

    session.start()
    assert session.status == GenerationStatus.RUNNING
    assert session.is_active
    print("  ✅ start() -> RUNNING")

    session.pause()
    assert session.status == GenerationStatus.PAUSED
    assert session.is_active
    print("  ✅ pause() -> PAUSED")

    session.resume()
    assert session.status == GenerationStatus.RUNNING
    print("  ✅ resume() -> RUNNING")

    session.request_stop()
    assert session.status == GenerationStatus.STOPPING
    assert session.should_stop
    print("  ✅ request_stop() -> STOPPING, should_stop=True")

    session.mark_stopped()
    assert session.status == GenerationStatus.STOPPED
    assert not session.is_active
    print("  ✅ mark_stopped() -> STOPPED")

    # 测试 complete
    session2 = GenerationSession(
        generation_id="gen_test2", conversation_id=1, user_id="u1", plan=plan,
    )
    session2.start()
    session2.complete()
    assert session2.status == GenerationStatus.COMPLETED
    print("  ✅ complete() -> COMPLETED")

    # 测试序列号
    session3 = GenerationSession(
        generation_id="gen_test3", conversation_id=1, user_id="u1", plan=plan,
    )
    assert session3.next_sequence() == 1
    assert session3.next_sequence() == 2
    assert session3.next_sequence() == 3
    print("  ✅ next_sequence() 递增正确")


def test_conversation_lock():
    """测试 ConversationLock 并发锁"""
    print("\n=== 测试 ConversationLock ===")
    lock_mgr = ConversationLock()

    # 创建第一个 session
    plan1 = ResponsePlan(
        mode=ChatMode.NORMAL, speakers=[1], conversation_id=100, user_id="u1",
    )

    async def _test():
        session1 = await lock_mgr.acquire(100, plan1)
        assert session1.is_active or session1.status == GenerationStatus.IDLE
        session1.start()
        assert lock_mgr.get_active_session(100) is session1
        print("  ✅ 第一个 session 获取锁成功")

        # 尝试获取第二个 session（应该冲突）
        plan2 = ResponsePlan(
            mode=ChatMode.NORMAL, speakers=[2], conversation_id=100, user_id="u1",
        )
        try:
            await lock_mgr.acquire(100, plan2)
            assert False, "应该抛出 GenerationConflictError"
        except GenerationConflictError as e:
            print(f"  ✅ 第二个 session 被正确拒绝: {e}")
            assert e.existing_session is session1

        # 停止第一个 session 并释放锁
        session1.request_stop()
        session1.mark_stopped()
        lock_mgr.release(100)

        # 现在应该可以获取新的 session
        session3 = await lock_mgr.acquire(100, plan2)
        assert session3 is not None
        print("  ✅ 释放锁后，第三个 session 获取成功")
        lock_mgr.release(100)

    asyncio.run(_test())


def test_orchestrator_plan():
    """测试 Orchestrator.plan() 规划功能"""
    print("\n=== 测试 Orchestrator.plan() ===")
    orch = ConversationOrchestrator()
    chars = [MockCharacter(1, "小雅"), MockCharacter(2, "小王"), MockCharacter(3, "老师")]

    # 测试指定角色
    plan1 = orch.plan(
        mode=ChatMode.NORMAL,
        strategy=SpeakerStrategy.SPECIFIC,
        user_message="你好",
        conversation_id=1,
        user_id="u1",
        characters=chars,
        specified_character_id=2,
    )
    assert plan1.speakers == [2]
    print("  ✅ 指定角色策略: speakers=[2]")

    # 测试 @角色
    plan2 = orch.plan(
        mode=ChatMode.NORMAL,
        strategy=SpeakerStrategy.MENTION,
        user_message="@小雅 @小王 你们好",
        conversation_id=1,
        user_id="u1",
        characters=chars,
        mentioned_character_ids=[1, 2],
    )
    assert plan2.speakers == [1, 2]
    print("  ✅ @角色策略: speakers=[1, 2]")

    # 测试群聊
    plan3 = orch.plan(
        mode=ChatMode.GROUP,
        strategy=SpeakerStrategy.SPECIFIC,
        user_message="大家好",
        conversation_id=1,
        user_id="u1",
        characters=chars,
    )
    assert plan3.speakers == [1, 2, 3]
    print("  ✅ 群聊模式: speakers=[1, 2, 3]")

    # 测试智能路由（模拟 router 函数）
    def mock_router(msg, characters):
        if "老师" in msg:
            return [3]
        return [1]

    plan4 = orch.plan(
        mode=ChatMode.NORMAL,
        strategy=SpeakerStrategy.SMART,
        user_message="老师，我考试挂科了",
        conversation_id=1,
        user_id="u1",
        characters=chars,
        smart_router_fn=mock_router,
    )
    assert plan4.speakers == [3]
    print("  ✅ 智能路由: 识别到'老师' -> speakers=[3]")

    # 测试无效 speaker 过滤
    plan5 = orch.plan(
        mode=ChatMode.NORMAL,
        strategy=SpeakerStrategy.SPECIFIC,
        user_message="你好",
        conversation_id=1,
        user_id="u1",
        characters=chars,
        specified_character_id=999,  # 不存在的 ID
    )
    assert plan5.speakers == [1]  # 回退到第一个
    print("  ✅ 无效 speaker 回退到第一个角色")


def test_orchestrator_execute():
    """测试 Orchestrator.execute() 执行流程"""
    print("\n=== 测试 Orchestrator.execute() ===")
    orch = ConversationOrchestrator()
    chars = [MockCharacter(1, "小雅"), MockCharacter(2, "小王")]
    char_lookup = {1: chars[0], 2: chars[1]}

    plan = orch.plan(
        mode=ChatMode.NORMAL,
        strategy=SpeakerStrategy.MENTION,
        user_message="@小雅 @小王 你们好",
        conversation_id=200,
        user_id="u1",
        characters=chars,
        mentioned_character_ids=[1, 2],
    )

    # 模拟角色生成器
    async def mock_character_generator(session, character):
        yield {"type": "content", "character_id": character.id, "text": f"你好，我是{character.name}"}
        yield {"type": "content", "character_id": character.id, "text": "很高兴认识你"}

    async def _test():
        events = []
        async for event in orch.execute(plan, mock_character_generator, char_lookup):
            events.append(event)

        # 验证事件序列
        event_types = [e["type"] for e in events]
        print(f"  事件序列: {event_types}")

        assert "generation_started" in event_types
        assert "character_started" in event_types
        assert "content" in event_types
        assert "character_completed" in event_types
        assert "generation_completed" in event_types

        # 验证两个角色都执行了
        started_chars = [e["character_id"] for e in events if e["type"] == "character_started"]
        assert started_chars == [1, 2]
        print(f"  ✅ 两个角色按顺序执行: {started_chars}")

        # 验证所有事件都有 generation_id
        for e in events:
            assert "generation_id" in e, f"事件缺少 generation_id: {e}"
        print("  ✅ 所有事件都携带 generation_id")

        # 验证 session 已完成
        session = orch.get_session_by_id(plan.generation_id)
        assert session.status == GenerationStatus.COMPLETED
        print("  ✅ session 状态为 COMPLETED")

    asyncio.run(_test())


def test_orchestrator_stop():
    """测试生成过程中停止"""
    print("\n=== 测试生成过程中停止 ===")
    orch = ConversationOrchestrator()
    chars = [MockCharacter(1, "小雅"), MockCharacter(2, "小王"), MockCharacter(3, "老师")]
    char_lookup = {c.id: c for c in chars}

    plan = orch.plan(
        mode=ChatMode.GROUP,
        strategy=SpeakerStrategy.SPECIFIC,
        user_message="大家好",
        conversation_id=300,
        user_id="u1",
        characters=chars,
    )

    # 模拟慢生成器，在第二个角色后停止
    call_count = 0

    async def slow_generator(session, character):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # 第二个角色执行时，触发停止
            orch.stop(300)
        yield {"type": "content", "character_id": character.id, "text": f"我是{character.name}"}
        await asyncio.sleep(0.01)

    async def _test():
        events = []
        async for event in orch.execute(plan, slow_generator, char_lookup):
            events.append(event)

        event_types = [e["type"] for e in events]
        print(f"  事件序列: {event_types}")

        # 应该在第二个角色后停止，第三个角色不执行
        started_chars = [e["character_id"] for e in events if e["type"] == "character_started"]
        print(f"  执行的角色: {started_chars}")
        assert len(started_chars) <= 2, "停止后不应该执行第三个角色"

        assert "generation_stopped" in event_types
        print("  ✅ 生成被正确停止，generation_stopped 事件已发出")

        session = orch.get_session_by_id(plan.generation_id)
        assert session.status == GenerationStatus.STOPPED
        print("  ✅ session 状态为 STOPPED")

    asyncio.run(_test())


def test_concurrent_conflict():
    """测试并发请求冲突（模拟用户快速点击发送）"""
    print("\n=== 测试并发请求冲突 ===")
    orch = ConversationOrchestrator()
    chars = [MockCharacter(1, "小雅")]
    char_lookup = {1: chars[0]}

    async def slow_generator(session, character):
        await asyncio.sleep(0.1)
        yield {"type": "content", "character_id": character.id, "text": "你好"}

    async def _test():
        plan1 = orch.plan(
            mode=ChatMode.NORMAL, strategy=SpeakerStrategy.SPECIFIC,
            user_message="第一条", conversation_id=400, user_id="u1",
            characters=chars, specified_character_id=1,
        )
        plan2 = orch.plan(
            mode=ChatMode.NORMAL, strategy=SpeakerStrategy.SPECIFIC,
            user_message="第二条", conversation_id=400, user_id="u1",
            characters=chars, specified_character_id=1,
        )

        # 同时发起两个请求
        results = []

        async def run_plan(plan):
            try:
                async for event in orch.execute(plan, slow_generator, char_lookup):
                    pass
                results.append(("success", plan.generation_id))
            except GenerationConflictError as e:
                results.append(("conflict", str(e)))

        await asyncio.gather(run_plan(plan1), run_plan(plan2))

        print(f"  结果: {[r[0] for r in results]}")
        assert any(r[0] == "success" for r in results), "至少一个应该成功"
        assert any(r[0] == "conflict" for r in results), "至少一个应该冲突"
        print("  ✅ 并发请求正确处理：一个成功，一个被拒绝")

    asyncio.run(_test())


def test_sequence_order():
    """测试消息序列号保证顺序"""
    print("\n=== 测试消息序列号 ===")
    orch = ConversationOrchestrator()
    chars = [MockCharacter(1, "小雅"), MockCharacter(2, "小王")]
    char_lookup = {c.id: c for c in chars}

    plan = orch.plan(
        mode=ChatMode.GROUP, strategy=SpeakerStrategy.SPECIFIC,
        user_message="大家好", conversation_id=500, user_id="u1",
        characters=chars,
    )

    async def generator(session, character):
        seq = session.next_sequence()
        yield {"type": "content", "character_id": character.id, "text": "消息", "sequence": seq}

    async def _test():
        sequences = []
        async for event in orch.execute(plan, generator, char_lookup):
            if event["type"] == "content":
                sequences.append(event["sequence"])

        print(f"  序列号: {sequences}")
        assert sequences == sorted(sequences), "序列号必须递增"
        assert len(sequences) == 2
        print("  ✅ 消息序列号严格递增，保证顺序")

    asyncio.run(_test())


if __name__ == "__main__":
    print("=" * 60)
    print("Chat Core 2.0 Phase 1 - 单元测试")
    print("=" * 60)

    test_response_plan()
    test_generation_session_state_machine()
    test_conversation_lock()
    test_orchestrator_plan()
    test_orchestrator_execute()
    test_orchestrator_stop()
    test_concurrent_conflict()
    test_sequence_order()

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
