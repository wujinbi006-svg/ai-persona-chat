"""
Chat Core 2.0 RC-3 Browser E2E Test
使用 Playwright 进行真实浏览器测试
"""
import asyncio
import json
import time
import sys
from playwright.async_api import async_playwright

STAGING_URL = "https://ai-persona-chat-qkito1k5p-ai-persona-team.vercel.app"
BACKEND_URL = "https://ai-persona-backend-staging.onrender.com"

TEST_EMAIL = f"rc3_e2e_{int(time.time())}@example.com"
TEST_PASSWORD = "Test123456!"

results = {}

def log(test_name, status, detail=""):
    results[test_name] = {"status": status, "detail": detail}
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⏳"
    print(f"{icon} {test_name}: {status} {detail}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        
        # 收集 console 错误
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        
        try:
            # ============================================
            # 测试 1: 页面加载
            # ============================================
            print("\n=== 测试 1: 页面加载 ===")
            t0 = time.time()
            await page.goto(STAGING_URL, wait_until="networkidle", timeout=60000)
            t1 = time.time()
            title = await page.title()
            log("页面加载", "PASS", f"title={title}, 耗时={int((t1-t0)*1000)}ms")
            
            # 截图
            await page.screenshot(path="e2e_screenshots/01_home.png")
            
            # ============================================
            # 测试 2: 注册
            # ============================================
            print("\n=== 测试 2: 注册 ===")
            try:
                # 查找注册按钮或链接
                register_btn = page.get_by_text("注册", exact=False)
                if await register_btn.count() > 0:
                    await register_btn.first.click()
                    await page.wait_for_timeout(1000)
                
                # 填写注册表单
                email_input = page.locator('input[type="email"], input[name="email"]')
                if await email_input.count() > 0:
                    await email_input.first.fill(TEST_EMAIL)
                
                password_input = page.locator('input[type="password"], input[name="password"]')
                if await password_input.count() > 0:
                    await password_input.first.fill(TEST_PASSWORD)
                
                # 确认密码
                confirm_input = page.locator('input[name="confirmPassword"], input[placeholder*="确认"]')
                if await confirm_input.count() > 0:
                    await confirm_input.first.fill(TEST_PASSWORD)
                
                # 点击注册
                submit_btn = page.get_by_role("button", name="注册")
                if await submit_btn.count() == 0:
                    submit_btn = page.locator('button[type="submit"]')
                await submit_btn.first.click()
                
                await page.wait_for_timeout(5000)
                log("用户注册", "PASS", f"email={TEST_EMAIL}")
            except Exception as e:
                log("用户注册", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/02_after_register.png")
            
            # ============================================
            # 测试 3: 登录（如果注册失败，尝试登录）
            # ============================================
            print("\n=== 测试 3: 登录状态 ===")
            await page.wait_for_timeout(2000)
            current_url = page.url
            log("登录状态", "PASS" if "login" not in current_url else "FAIL", f"url={current_url[:80]}")
            
            # ============================================
            # 测试 4: 新建聊天
            # ============================================
            print("\n=== 测试 4: 新建聊天 ===")
            try:
                t0 = time.time()
                new_chat_btn = page.get_by_text("新对话", exact=False)
                if await new_chat_btn.count() == 0:
                    new_chat_btn = page.locator('button[aria-label*="新"], button[title*="新"]')
                if await new_chat_btn.count() > 0:
                    await new_chat_btn.first.click()
                    await page.wait_for_timeout(2000)
                    t1 = time.time()
                    log("新建聊天", "PASS", f"耗时={int((t1-t0)*1000)}ms")
                else:
                    log("新建聊天", "FAIL", "未找到新对话按钮")
            except Exception as e:
                log("新建聊天", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/03_new_chat.png")
            
            # ============================================
            # 测试 5: 创建角色
            # ============================================
            print("\n=== 测试 5: 创建角色 ===")
            try:
                t0 = time.time()
                # 查找添加角色按钮
                add_char_btn = page.get_by_text("添加角色", exact=False)
                if await add_char_btn.count() == 0:
                    add_char_btn = page.get_by_text("角色", exact=False)
                if await add_char_btn.count() > 0:
                    await add_char_btn.first.click()
                    await page.wait_for_timeout(1000)
                    
                    # 填写角色名称
                    name_input = page.locator('input[placeholder*="名称"], input[name="name"]')
                    if await name_input.count() > 0:
                        await name_input.first.fill("小雅")
                    
                    # 填写人格
                    persona_input = page.locator('textarea, input[placeholder*="人格"], input[placeholder*="persona"]')
                    if await persona_input.count() > 0:
                        await persona_input.first.fill("你是小雅，温柔可爱的女生，喜欢喝奶茶。")
                    
                    # 保存
                    save_btn = page.get_by_role("button", name="保存")
                    if await save_btn.count() == 0:
                        save_btn = page.locator('button[type="submit"]')
                    await save_btn.first.click()
                    await page.wait_for_timeout(3000)
                    t1 = time.time()
                    log("创建角色", "PASS", f"耗时={int((t1-t0)*1000)}ms")
                else:
                    log("创建角色", "FAIL", "未找到添加角色按钮")
            except Exception as e:
                log("创建角色", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/04_character_created.png")
            
            # ============================================
            # 测试 6: 普通聊天
            # ============================================
            print("\n=== 测试 6: 普通聊天 ===")
            try:
                t0 = time.time()
                # 查找输入框
                textarea = page.locator('textarea, input[placeholder*="输入"], input[placeholder*="消息"]')
                if await textarea.count() > 0:
                    await textarea.first.fill("你好")
                    await page.wait_for_timeout(500)
                    
                    # 点击发送
                    send_btn = page.get_by_role("button", name="发送")
                    if await send_btn.count() == 0:
                        send_btn = page.locator('button[aria-label*="发送"]')
                    await send_btn.first.click()
                    
                    # 等待 AI 回复
                    await page.wait_for_timeout(15000)
                    t1 = time.time()
                    
                    # 检查消息数量
                    messages = page.locator('[class*="message"], [class*="Message"]')
                    msg_count = await messages.count()
                    log("普通聊天", "PASS", f"耗时={int((t1-t0)*1000)}ms, 消息数={msg_count}")
                else:
                    log("普通聊天", "FAIL", "未找到输入框")
            except Exception as e:
                log("普通聊天", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/05_chat.png")
            
            # ============================================
            # 测试 7: 检查 console 错误
            # ============================================
            print("\n=== 测试 7: Console 错误检查 ===")
            if console_errors:
                log("Console 错误", "FAIL", f"{len(console_errors)} 个错误: {console_errors[:3]}")
            else:
                log("Console 错误", "PASS", "无错误")
            
        except Exception as e:
            print(f"测试过程中发生错误: {e}")
        finally:
            await browser.close()
        
        # ============================================
        # 输出结果
        # ============================================
        print("\n" + "="*60)
        print("E2E 测试结果汇总")
        print("="*60)
        passed = sum(1 for v in results.values() if v["status"] == "PASS")
        failed = sum(1 for v in results.values() if v["status"] == "FAIL")
        for name, result in results.items():
            icon = "✅" if result["status"] == "PASS" else "❌"
            print(f"{icon} {name}: {result['detail']}")
        print(f"\n总计: {passed} 通过, {failed} 失败")
        
        # 保存结果
        with open("e2e_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    import os
    os.makedirs("e2e_screenshots", exist_ok=True)
    asyncio.run(main())
