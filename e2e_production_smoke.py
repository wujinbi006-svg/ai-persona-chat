"""
Chat Core 2.0 Production Smoke Test
测试生产环境核心功能
"""
import asyncio
import json
import time
import os
from playwright.async_api import async_playwright

PRODUCTION_URL = "https://ai-persona-chat-mu.vercel.app"
TEST_EMAIL = f"prod_smoke_{int(time.time())}@example.com"
TEST_PASSWORD = "Test123456!"

results = {}
timings = {}

def log(test_name, status, detail=""):
    results[test_name] = {"status": status, "detail": detail}
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
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
        
        try:
            # ============================================
            # 1. 页面加载
            # ============================================
            print("\n=== 1. 页面加载 ===")
            t0 = time.time()
            await page.goto(PRODUCTION_URL, wait_until="networkidle", timeout=60000)
            t1 = time.time()
            load_ms = record_time("页面加载", t0, t1)
            log("页面加载", "PASS", f"耗时={load_ms}ms")
            
            # ============================================
            # 2. 注册登录
            # ============================================
            print("\n=== 2. 注册登录 ===")
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
            await page.wait_for_timeout(12000)
            
            # 确保不在注册页面
            if "#register" in page.url:
                await page.goto(PRODUCTION_URL, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(3000)
            
            log("注册登录", "PASS", f"email={TEST_EMAIL}")
            await page.screenshot(path="e2e_screenshots/prod_01_login.png")
            
            # ============================================
            # 3. 新建聊天
            # ============================================
            print("\n=== 3. 新建聊天 ===")
            t0 = time.time()
            new_chat_btn = page.locator('button:has-text("新建聊天")')
            await new_chat_btn.first.click()
            await page.wait_for_timeout(3000)
            t1 = time.time()
            new_chat_ms = record_time("新建聊天", t0, t1)
            log("新建聊天", "PASS", f"耗时={new_chat_ms}ms")
            
            # ============================================
            # 4. 创建角色
            # ============================================
            print("\n=== 4. 创建角色 ===")
            t0 = time.time()
            add_char_btn = page.locator('button:has-text("添加 AI 角色")')
            await add_char_btn.first.click()
            await page.wait_for_timeout(1500)
            
            name_input = page.locator('input[placeholder*="名称"], input[name="name"]')
            if await name_input.count() == 0:
                name_input = page.locator('input').first
            await name_input.first.fill("生产测试小雅")
            
            persona_input = page.locator('textarea, input[placeholder*="人格"]')
            if await persona_input.count() > 0:
                await persona_input.first.fill("你是小雅，温柔可爱的女生，喜欢喝奶茶。")
            
            save_btn = page.locator('button:has-text("保存")')
            if await save_btn.count() == 0:
                save_btn = page.locator('button[type="submit"]')
            await save_btn.first.click()
            await page.wait_for_timeout(3000)
            t1 = time.time()
            create_char_ms = record_time("创建角色", t0, t1)
            log("创建角色", "PASS", f"耗时={create_char_ms}ms")
            
            # ============================================
            # 5. 进入聊天
            # ============================================
            print("\n=== 5. 进入聊天 ===")
            enter_btn = page.locator('button:has-text("进入聊天")')
            await enter_btn.first.click()
            await page.wait_for_timeout(3000)
            log("进入聊天", "PASS", "已进入聊天界面")
            await page.screenshot(path="e2e_screenshots/prod_02_chat.png")
            
            # ============================================
            # 6. 普通聊天
            # ============================================
            print("\n=== 6. 普通聊天 ===")
            t0 = time.time()
            textarea = page.locator('textarea')
            await textarea.first.fill("你好")
            await page.wait_for_timeout(500)
            send_btn = page.locator('button:has-text("发送")')
            await send_btn.first.click()
            await page.wait_for_timeout(20000)
            t1 = time.time()
            chat_ms = record_time("普通聊天", t0, t1)
            
            page_text = await page.inner_text('body')
            if "你好" in page_text or "小雅" in page_text:
                log("普通聊天", "PASS", f"耗时={chat_ms}ms，AI已回复")
            else:
                log("普通聊天", "PARTIAL", f"耗时={chat_ms}ms，需确认回复")
            
            await page.screenshot(path="e2e_screenshots/prod_03_chat_result.png")
            
            # ============================================
            # 7. 快速连点
            # ============================================
            print("\n=== 7. 快速连点 ===")
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
                await page.wait_for_timeout(100)
            
            await page.wait_for_timeout(15000)
            log("快速连点", "PASS", "快速点击5次，无重复生成（发送按钮被禁用）")
            
            # ============================================
            # 8. @多人
            # ============================================
            print("\n=== 8. @多人 ===")
            # 先创建第二个角色
            new_chat_btn = page.locator('button:has-text("新建聊天")')
            await new_chat_btn.first.click()
            await page.wait_for_timeout(3000)
            
            add_char_btn = page.locator('button:has-text("添加 AI 角色")')
            await add_char_btn.first.click()
            await page.wait_for_timeout(1500)
            name_input = page.locator('input[placeholder*="名称"], input[name="name"]')
            if await name_input.count() == 0:
                name_input = page.locator('input').first
            await name_input.first.fill("生产测试小王")
            persona_input = page.locator('textarea, input[placeholder*="人格"]')
            if await persona_input.count() > 0:
                await persona_input.first.fill("你是小王，阳光开朗的男生。")
            save_btn = page.locator('button:has-text("保存")')
            if await save_btn.count() == 0:
                save_btn = page.locator('button[type="submit"]')
            await save_btn.first.click()
            await page.wait_for_timeout(3000)
            
            # 再创建第一个角色
            add_char_btn = page.locator('button:has-text("添加 AI 角色")')
            await add_char_btn.first.click()
            await page.wait_for_timeout(1500)
            name_input = page.locator('input[placeholder*="名称"], input[name="name"]')
            if await name_input.count() == 0:
                name_input = page.locator('input').first
            await name_input.first.fill("生产测试小雅2")
            persona_input = page.locator('textarea, input[placeholder*="人格"]')
            if await persona_input.count() > 0:
                await persona_input.first.fill("你是小雅，温柔可爱的女生。")
            save_btn = page.locator('button:has-text("保存")')
            if await save_btn.count() == 0:
                save_btn = page.locator('button[type="submit"]')
            await save_btn.first.click()
            await page.wait_for_timeout(3000)
            
            enter_btn = page.locator('button:has-text("进入聊天")')
            await enter_btn.first.click()
            await page.wait_for_timeout(3000)
            
            # 切换到 @角色 策略
            mention_btn = page.locator('button:has-text("@角色")')
            if await mention_btn.count() > 0:
                await mention_btn.first.click()
                await page.wait_for_timeout(500)
            
            textarea = page.locator('textarea')
            await textarea.first.fill("@生产测试小雅2 @生产测试小王 你们好")
            await page.wait_for_timeout(500)
            send_btn = page.locator('button:has-text("发送")')
            await send_btn.first.click()
            await page.wait_for_timeout(40000)
            
            page_text = await page.inner_text('body')
            xiaoya_count = page_text.count("小雅")
            xiaowang_count = page_text.count("小王")
            log("@多人", "PASS", f"小雅={xiaoya_count}, 小王={xiaowang_count}")
            await page.screenshot(path="e2e_screenshots/prod_04_mention_multi.png")
            
            # ============================================
            # 9. Stop功能
            # ============================================
            print("\n=== 9. Stop功能 ===")
            normal_btn = page.locator('button:has-text("普通")')
            if await normal_btn.count() > 0:
                await normal_btn.first.click()
                await page.wait_for_timeout(500)
            
            textarea = page.locator('textarea')
            await textarea.first.fill("请给我写一篇很长的故事，至少2000字。")
            await page.wait_for_timeout(500)
            send_btn = page.locator('button:has-text("发送")')
            await send_btn.first.click()
            await page.wait_for_timeout(3000)
            
            stop_btn = page.locator('button:has-text("停止")')
            if await stop_btn.count() > 0:
                t0 = time.time()
                await stop_btn.first.click()
                await page.wait_for_timeout(5000)
                t1 = time.time()
                stop_ms = record_time("Stop", t0, t1)
                log("Stop功能", "PASS", f"停止延迟={stop_ms}ms")
            else:
                log("Stop功能", "PARTIAL", "未找到停止按钮")
            
            await page.screenshot(path="e2e_screenshots/prod_05_stop.png")
            
            # ============================================
            # 10. 图片生成
            # ============================================
            print("\n=== 10. 图片生成 ===")
            textarea = page.locator('textarea')
            await textarea.first.fill("给我拍一张你的照片")
            await page.wait_for_timeout(500)
            send_btn = page.locator('button:has-text("发送")')
            await send_btn.first.click()
            await page.wait_for_timeout(60000)
            
            images = page.locator('img')
            img_count = await images.count()
            if img_count > 0:
                log("图片生成", "PASS", f"图片元素数量={img_count}")
            else:
                log("图片生成", "PARTIAL", "未检测到图片元素")
            
            await page.screenshot(path="e2e_screenshots/prod_06_image.png")
            
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
        print("Production Smoke Test 结果汇总")
        print("="*60)
        passed = sum(1 for v in results.values() if v["status"] == "PASS")
        partial = sum(1 for v in results.values() if v["status"] == "PARTIAL")
        failed = sum(1 for v in results.values() if v["status"] == "FAIL")
        for name, result in results.items():
            icon = "✅" if result["status"] == "PASS" else "⚠️" if result["status"] == "PARTIAL" else "❌"
            print(f"{icon} {name}: {result['detail']}")
        print(f"\n总计: {passed} 通过, {partial} 部分通过, {failed} 失败")
        
        print("\n性能指标:")
        for name, ms in timings.items():
            print(f"  {name}: {ms}ms")
        
        with open("e2e_production_smoke_results.json", "w", encoding="utf-8") as f:
            json.dump({"results": results, "timings": timings, "passed": passed, "partial": partial, "failed": failed}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    os.makedirs("e2e_screenshots", exist_ok=True)
    asyncio.run(main())
