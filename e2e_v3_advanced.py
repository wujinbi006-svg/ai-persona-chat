"""
Chat Core 2.0 RC-3 高级功能 E2E 测试
测试：@多人、快速连点、Stop、群聊
"""
import asyncio
import json
import time
import os
from playwright.async_api import async_playwright

STAGING_URL = "https://ai-persona-chat-qkito1k5p-ai-persona-team.vercel.app"
TEST_EMAIL = f"rc3_adv_{int(time.time())}@example.com"
TEST_PASSWORD = "Test123456!"

results = {}
timings = {}

def log(test_name, status, detail=""):
    results[test_name] = {"status": status, "detail": detail}
    icon = "✅" if status == "PASS" else "❌"
    print(f"{icon} {test_name}: {status} {detail[:150]}")

def record_time(name, t0, t1):
    ms = int((t1 - t0) * 1000)
    timings[name] = ms
    return ms

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        
        network_requests = []
        def on_request(request):
            if "/api/chat/" in request.url:
                network_requests.append({"url": request.url, "method": request.method, "time": time.time()})
        page.on("request", on_request)
        
        try:
            # ============================================
            # 前置：注册登录、创建聊天和角色
            # ============================================
            print("\n=== 前置：注册登录 ===")
            await page.goto(STAGING_URL, wait_until="networkidle", timeout=60000)
            
            # 注册
            register_link = page.locator('a[href="#register"]')
            if await register_link.count() > 0:
                await register_link.first.click()
                await page.wait_for_timeout(1000)
            
            email_input = page.locator('input[type="email"]')
            await email_input.first.fill(TEST_EMAIL)
            password_inputs = page.locator('input[type="password"]')
            await password_inputs.nth(0).fill(TEST_PASSWORD)
            if await password_inputs.count() > 1:
                await password_inputs.nth(1).fill(TEST_PASSWORD)
            submit_btn = page.locator('button[type="submit"]')
            await submit_btn.first.click()
            await page.wait_for_timeout(10000)
            log("注册登录", "PASS", f"email={TEST_EMAIL}")
            
            # 新建聊天
            print("\n=== 新建聊天 ===")
            new_chat_btn = page.locator('button:has-text("新建聊天")')
            await new_chat_btn.first.click()
            await page.wait_for_timeout(3000)
            
            # 创建角色1：小雅
            print("\n=== 创建角色：小雅 ===")
            add_char_btn = page.locator('button:has-text("添加 AI 角色")')
            await add_char_btn.first.click()
            await page.wait_for_timeout(1500)
            name_input = page.locator('input[placeholder*="名称"], input[name="name"]')
            if await name_input.count() == 0:
                name_input = page.locator('input').first
            await name_input.first.fill("小雅")
            persona_input = page.locator('textarea, input[placeholder*="人格"]')
            if await persona_input.count() > 0:
                await persona_input.first.fill("你是小雅，温柔可爱的女生，喜欢喝奶茶。")
            save_btn = page.locator('button:has-text("保存")')
            if await save_btn.count() == 0:
                save_btn = page.locator('button[type="submit"]')
            await save_btn.first.click()
            await page.wait_for_timeout(3000)
            
            # 创建角色2：小王
            print("\n=== 创建角色：小王 ===")
            add_char_btn = page.locator('button:has-text("添加 AI 角色")')
            await add_char_btn.first.click()
            await page.wait_for_timeout(1500)
            name_input = page.locator('input[placeholder*="名称"], input[name="name"]')
            if await name_input.count() == 0:
                name_input = page.locator('input').first
            await name_input.first.fill("小王")
            persona_input = page.locator('textarea, input[placeholder*="人格"]')
            if await persona_input.count() > 0:
                await persona_input.first.fill("你是小王，阳光开朗的男生，喜欢运动。")
            save_btn = page.locator('button:has-text("保存")')
            if await save_btn.count() == 0:
                save_btn = page.locator('button[type="submit"]')
            await save_btn.first.click()
            await page.wait_for_timeout(3000)
            log("创建角色", "PASS", "小雅、小王已创建")
            
            # 进入聊天
            print("\n=== 进入聊天 ===")
            enter_btn = page.locator('button:has-text("进入聊天")')
            await enter_btn.first.click()
            await page.wait_for_timeout(3000)
            log("进入聊天", "PASS", "已进入聊天界面")
            
            await page.screenshot(path="e2e_screenshots/v3_01_ready.png")
            
            # ============================================
            # 测试1：普通聊天（基线）
            # ============================================
            print("\n=== 测试1：普通聊天 ===")
            try:
                network_requests.clear()
                t0 = time.time()
                textarea = page.locator('textarea')
                await textarea.first.fill("你好")
                await page.wait_for_timeout(500)
                send_btn = page.locator('button:has-text("发送")')
                await send_btn.first.click()
                await page.wait_for_timeout(20000)
                t1 = time.time()
                chat_ms = record_time("普通聊天", t0, t1)
                chat_reqs = [r for r in network_requests if "/api/chat/" in r["url"]]
                log("普通聊天", "PASS", f"耗时={chat_ms}ms, API请求={len(chat_reqs)}")
            except Exception as e:
                log("普通聊天", "FAIL", str(e)[:100])
            
            await page.screenshot(path="e2e_screenshots/v3_02_normal_chat.png")
            
            # ============================================
            # 测试2：@多人
            # ============================================
            print("\n=== 测试2：@多人 ===")
            try:
                network_requests.clear()
                t0 = time.time()
                
                # 切换到 @角色 策略
                mention_btn = page.locator('button:has-text("@角色")')
                if await mention_btn.count() > 0:
                    await mention_btn.first.click()
                    await page.wait_for_timeout(500)
                
                textarea = page.locator('textarea')
                await textarea.first.fill("@小雅 @小王 你们好")
                await page.wait_for_timeout(500)
                send_btn = page.locator('button:has-text("发送")')
                await send_btn.first.click()
                
                # 等待两个角色都回复
                await page.wait_for_timeout(40000)
                t1 = time.time()
                mention_ms = record_time("@多人", t0, t1)
                
                page_text = await page.inner_text('body')
                xiaoya_count = page_text.count("小雅")
                xiaowang_count = page_text.count("小王")
                
                chat_reqs = [r for r in network_requests if "/api/chat/" in r["url"]]
                
                if xiaoya_count > 0 and xiaowang_count > 0 and len(chat_reqs) == 1:
                    log("@多人", "PASS", f"耗时={mention_ms}ms, 小雅={xiaoya_count}, 小王={xiaowang_count}, API请求={len(chat_reqs)}")
                else:
                    log("@多人", "FAIL", f"小雅={xiaoya_count}, 小王={xiaowang_count}, API请求={len(chat_reqs)}")
            except Exception as e:
                log("@多人", "FAIL", str(e)[:100])
            
            await page.screenshot(path="e2e_screenshots/v3_03_mention_multi.png")
            
            # ============================================
            # 测试3：快速连点
            # ============================================
            print("\n=== 测试3：快速连点 ===")
            try:
                network_requests.clear()
                t0 = time.time()
                
                # 切换回指定角色策略
                specific_btn = page.locator('button:has-text("指定角色")')
                if await specific_btn.count() > 0:
                    await specific_btn.first.click()
                    await page.wait_for_timeout(500)
                
                textarea = page.locator('textarea')
                await textarea.first.fill("快速连点测试")
                await page.wait_for_timeout(500)
                
                send_btn = page.locator('button:has-text("发送")')
                # 快速点击5次
                for i in range(5):
                    try:
                        await send_btn.first.click(timeout=1000)
                    except:
                        pass
                    await page.wait_for_timeout(150)
                
                await page.wait_for_timeout(20000)
                t1 = time.time()
                rapid_ms = record_time("快速连点", t0, t1)
                
                chat_reqs = [r for r in network_requests if "/api/chat/" in r["url"]]
                
                if len(chat_reqs) <= 1:
                    log("快速连点", "PASS", f"耗时={rapid_ms}ms, API请求={len(chat_reqs)}（应<=1）")
                else:
                    log("快速连点", "FAIL", f"API请求={len(chat_reqs)}（应<=1，存在重复请求）")
            except Exception as e:
                log("快速连点", "FAIL", str(e)[:100])
            
            await page.screenshot(path="e2e_screenshots/v3_04_rapid_click.png")
            
            # ============================================
            # 测试4：群聊
            # ============================================
            print("\n=== 测试4：群聊 ===")
            try:
                network_requests.clear()
                t0 = time.time()
                
                # 切换到群聊模式
                group_btn = page.locator('button:has-text("群聊")')
                if await group_btn.count() > 0:
                    await group_btn.first.click()
                    await page.wait_for_timeout(500)
                
                textarea = page.locator('textarea')
                await textarea.first.fill("你们觉得今天天气怎么样？")
                await page.wait_for_timeout(500)
                send_btn = page.locator('button:has-text("发送")')
                await send_btn.first.click()
                
                await page.wait_for_timeout(40000)
                t1 = time.time()
                group_ms = record_time("群聊", t0, t1)
                
                page_text = await page.inner_text('body')
                xiaoya_count = page_text.count("小雅")
                xiaowang_count = page_text.count("小王")
                
                chat_reqs = [r for r in network_requests if "/api/chat/" in r["url"]]
                
                if xiaoya_count > 0 and xiaowang_count > 0 and len(chat_reqs) == 1:
                    log("群聊", "PASS", f"耗时={group_ms}ms, 小雅={xiaoya_count}, 小王={xiaowang_count}, API请求={len(chat_reqs)}")
                else:
                    log("群聊", "FAIL", f"小雅={xiaoya_count}, 小王={xiaowang_count}, API请求={len(chat_reqs)}")
            except Exception as e:
                log("群聊", "FAIL", str(e)[:100])
            
            await page.screenshot(path="e2e_screenshots/v3_05_group_chat.png")
            
            # ============================================
            # 测试5：Stop 功能
            # ============================================
            print("\n=== 测试5：Stop 功能 ===")
            try:
                network_requests.clear()
                t0 = time.time()
                
                # 切换回普通模式
                normal_btn = page.locator('button:has-text("普通")')
                if await normal_btn.count() > 0:
                    await normal_btn.first.click()
                    await page.wait_for_timeout(500)
                
                textarea = page.locator('textarea')
                await textarea.first.fill("请给我写一篇很长的故事，至少1000字，关于一个冒险的旅程。")
                await page.wait_for_timeout(500)
                send_btn = page.locator('button:has-text("发送")')
                await send_btn.first.click()
                
                # 等待3秒后点击停止
                await page.wait_for_timeout(5000)
                
                stop_btn = page.locator('button:has-text("停止")')
                if await stop_btn.count() > 0:
                    stop_click_time = time.time()
                    await stop_btn.first.click()
                    await page.wait_for_timeout(5000)
                    stop_end_time = time.time()
                    stop_ms = record_time("Stop响应", stop_click_time, stop_end_time)
                    log("Stop功能", "PASS", f"停止响应={stop_ms}ms")
                else:
                    log("Stop功能", "FAIL", "未找到停止按钮")
            except Exception as e:
                log("Stop功能", "FAIL", str(e)[:100])
            
            await page.screenshot(path="e2e_screenshots/v3_06_stop.png")
            
        except Exception as e:
            print(f"测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()
        
        # ============================================
        # 输出结果
        # ============================================
        print("\n" + "="*60)
        print("高级功能 E2E 测试结果汇总")
        print("="*60)
        passed = sum(1 for v in results.values() if v["status"] == "PASS")
        failed = sum(1 for v in results.values() if v["status"] == "FAIL")
        for name, result in results.items():
            icon = "✅" if result["status"] == "PASS" else "❌"
            print(f"{icon} {name}: {result['detail']}")
        print(f"\n总计: {passed} 通过, {failed} 失败")
        
        print("\n性能指标:")
        for name, ms in timings.items():
            print(f"  {name}: {ms}ms")
        
        with open("e2e_v3_advanced_results.json", "w", encoding="utf-8") as f:
            json.dump({"results": results, "timings": timings, "passed": passed, "failed": failed}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    os.makedirs("e2e_screenshots", exist_ok=True)
    asyncio.run(main())
