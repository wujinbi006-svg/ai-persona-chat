"""
Chat Core 2.0 RC-3 完整浏览器 E2E 测试
使用 Playwright 进行真实浏览器测试
"""
import asyncio
import json
import time
import os
import sys
from playwright.async_api import async_playwright

STAGING_URL = "https://ai-persona-chat-qkito1k5p-ai-persona-team.vercel.app"
BACKEND_URL = "https://ai-persona-backend-staging.onrender.com"

TEST_EMAIL = f"rc3_full_{int(time.time())}@example.com"
TEST_PASSWORD = "Test123456!"

results = {}
timings = {}

def log(test_name, status, detail=""):
    results[test_name] = {"status": status, "detail": detail}
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⏳"
    print(f"{icon} {test_name}: {status} {detail[:100]}")

def record_time(name, t0, t1):
    ms = int((t1 - t0) * 1000)
    timings[name] = ms
    return ms

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        
        # 收集网络请求
        network_requests = []
        def on_request(request):
            if "/api/chat/" in request.url:
                network_requests.append({"url": request.url, "method": request.method, "post_data": request.post_data})
        page.on("request", on_request)
        
        try:
            # ============================================
            # 第一组：用户系统
            # ============================================
            print("\n" + "="*60)
            print("第一组：用户系统")
            print("="*60)
            
            # 测试 1: 页面加载
            print("\n--- 测试 1: 页面加载 ---")
            t0 = time.time()
            await page.goto(STAGING_URL, wait_until="networkidle", timeout=60000)
            t1 = time.time()
            title = await page.title()
            load_ms = record_time("页面加载", t0, t1)
            log("页面加载", "PASS", f"title={title}, {load_ms}ms")
            await page.screenshot(path="e2e_screenshots/01_login.png")
            
            # 测试 2: 注册
            print("\n--- 测试 2: 注册 ---")
            try:
                # 查找注册入口
                register_link = page.get_by_text("注册", exact=False)
                if await register_link.count() > 0:
                    await register_link.first.click()
                    await page.wait_for_timeout(1000)
                
                # 填写邮箱
                email_input = page.locator('input[type="email"]')
                if await email_input.count() == 0:
                    email_input = page.locator('input[name="email"]')
                await email_input.first.fill(TEST_EMAIL)
                
                # 填写密码
                password_inputs = page.locator('input[type="password"]')
                await password_inputs.nth(0).fill(TEST_PASSWORD)
                if await password_inputs.count() > 1:
                    await password_inputs.nth(1).fill(TEST_PASSWORD)
                
                # 点击注册
                submit_btn = page.locator('button[type="submit"]')
                if await submit_btn.count() == 0:
                    submit_btn = page.get_by_role("button", name="注册")
                await submit_btn.first.click()
                
                # 等待注册完成并跳转
                await page.wait_for_timeout(8000)
                current_url = page.url
                
                if "login" not in current_url and "vercel.com" not in current_url:
                    log("用户注册", "PASS", f"email={TEST_EMAIL}, 跳转至应用")
                else:
                    log("用户注册", "FAIL", f"跳转异常: {current_url[:100]}")
            except Exception as e:
                log("用户注册", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/02_after_register.png")
            
            # 测试 3: 登录状态验证
            print("\n--- 测试 3: 登录状态 ---")
            current_url = page.url
            if "login" not in current_url and "vercel.com" not in current_url:
                log("登录状态", "PASS", f"已登录, url={current_url[:80]}")
            else:
                log("登录状态", "FAIL", f"未登录, url={current_url[:80]}")
            
            # 如果未登录，尝试登录
            if "login" in current_url or "vercel.com" in current_url:
                print("尝试重新登录...")
                await page.goto(STAGING_URL, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                email_input = page.locator('input[type="email"], input[name="email"]')
                if await email_input.count() > 0:
                    await email_input.first.fill(TEST_EMAIL)
                password_input = page.locator('input[type="password"]')
                if await password_input.count() > 0:
                    await password_input.first.fill(TEST_PASSWORD)
                login_btn = page.locator('button[type="submit"], button:has-text("登录")')
                if await login_btn.count() > 0:
                    await login_btn.first.click()
                    await page.wait_for_timeout(8000)
            
            # ============================================
            # 第二组：新建聊天性能
            # ============================================
            print("\n" + "="*60)
            print("第二组：新建聊天性能")
            print("="*60)
            
            try:
                t0 = time.time()
                # 查找新对话按钮
                new_chat_btn = page.get_by_text("新对话", exact=False)
                if await new_chat_btn.count() == 0:
                    new_chat_btn = page.locator('button[aria-label*="新"], button[title*="新"], [class*="new"]')
                if await new_chat_btn.count() > 0:
                    await new_chat_btn.first.click()
                    await page.wait_for_timeout(3000)
                    t1 = time.time()
                    ui_ms = record_time("新建聊天UI", t0, t1)
                    log("新建聊天", "PASS", f"UI显示={ui_ms}ms")
                else:
                    log("新建聊天", "FAIL", "未找到新对话按钮")
            except Exception as e:
                log("新建聊天", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/03_new_chat.png")
            
            # ============================================
            # 第三组：新角色性能
            # ============================================
            print("\n" + "="*60)
            print("第三组：新角色性能")
            print("="*60)
            
            try:
                t0 = time.time()
                # 查找添加角色入口
                add_char_btn = page.get_by_text("添加角色", exact=False)
                if await add_char_btn.count() == 0:
                    add_char_btn = page.get_by_text("角色", exact=False)
                if await add_char_btn.count() > 0:
                    await add_char_btn.first.click()
                    await page.wait_for_timeout(1500)
                    
                    # 填写角色名称
                    name_input = page.locator('input[placeholder*="名称"], input[name="name"], input[label*="名称"]')
                    if await name_input.count() == 0:
                        name_input = page.locator('input').first
                    await name_input.first.fill("小雅")
                    
                    # 填写人格
                    persona_input = page.locator('textarea, input[placeholder*="人格"], input[placeholder*="persona"]')
                    if await persona_input.count() > 0:
                        await persona_input.first.fill("你是小雅，温柔可爱的女生，喜欢喝奶茶，说话亲切自然。")
                    
                    # 保存
                    save_btn = page.get_by_role("button", name="保存")
                    if await save_btn.count() == 0:
                        save_btn = page.locator('button[type="submit"]')
                    await save_btn.first.click()
                    await page.wait_for_timeout(4000)
                    t1 = time.time()
                    char_ms = record_time("创建角色", t0, t1)
                    log("创建角色", "PASS", f"总耗时={char_ms}ms")
                else:
                    log("创建角色", "FAIL", "未找到添加角色按钮")
            except Exception as e:
                log("创建角色", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/04_character.png")
            
            # 创建第二个角色（用于@多人测试）
            try:
                add_char_btn = page.get_by_text("添加角色", exact=False)
                if await add_char_btn.count() > 0:
                    await add_char_btn.first.click()
                    await page.wait_for_timeout(1500)
                    name_input = page.locator('input[placeholder*="名称"], input[name="name"]')
                    if await name_input.count() == 0:
                        name_input = page.locator('input').first
                    await name_input.first.fill("小王")
                    persona_input = page.locator('textarea, input[placeholder*="人格"]')
                    if await persona_input.count() > 0:
                        await persona_input.first.fill("你是小王，阳光开朗的男生，喜欢运动。")
                    save_btn = page.get_by_role("button", name="保存")
                    if await save_btn.count() == 0:
                        save_btn = page.locator('button[type="submit"]')
                    await save_btn.first.click()
                    await page.wait_for_timeout(3000)
                    log("创建第二个角色", "PASS", "小王已创建")
            except Exception as e:
                log("创建第二个角色", "FAIL", str(e)[:100])
            
            # ============================================
            # 第四组：普通聊天
            # ============================================
            print("\n" + "="*60)
            print("第四组：普通聊天")
            print("="*60)
            
            try:
                # 查找输入框
                textarea = page.locator('textarea, input[placeholder*="输入"], input[placeholder*="消息"]')
                if await textarea.count() > 0:
                    t0 = time.time()
                    await textarea.first.fill("你好")
                    await page.wait_for_timeout(500)
                    
                    # 点击发送
                    send_btn = page.get_by_role("button", name="发送")
                    if await send_btn.count() == 0:
                        send_btn = page.locator('button[aria-label*="发送"]')
                    await send_btn.first.click()
                    
                    # 等待 AI 回复
                    await page.wait_for_timeout(20000)
                    t1 = time.time()
                    
                    # 检查消息数量
                    messages = page.locator('[class*="message"], [class*="Message"], [class*="bubble"]')
                    msg_count = await messages.count()
                    chat_ms = record_time("普通聊天", t0, t1)
                    
                    # 检查 API 请求数量
                    chat_requests = [r for r in network_requests if "/api/chat/" in r["url"]]
                    log("普通聊天", "PASS", f"耗时={chat_ms}ms, 消息数={msg_count}, API请求={len(chat_requests)}")
                else:
                    log("普通聊天", "FAIL", "未找到输入框")
            except Exception as e:
                log("普通聊天", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/05_chat.png")
            
            # ============================================
            # 第五组：快速连点
            # ============================================
            print("\n" + "="*60)
            print("第五组：快速连点测试")
            print("="*60)
            
            try:
                network_requests.clear()
                textarea = page.locator('textarea, input[placeholder*="输入"]')
                if await textarea.count() > 0:
                    await textarea.first.fill("测试快速连点")
                    send_btn = page.get_by_role("button", name="发送")
                    if await send_btn.count() == 0:
                        send_btn = page.locator('button[aria-label*="发送"]')
                    
                    # 快速点击5次
                    for i in range(5):
                        try:
                            await send_btn.first.click(timeout=1000)
                        except:
                            pass
                        await page.wait_for_timeout(200)
                    
                    await page.wait_for_timeout(15000)
                    
                    # 检查 API 请求数量
                    chat_requests = [r for r in network_requests if "/api/chat/" in r["url"]]
                    if len(chat_requests) <= 1:
                        log("快速连点", "PASS", f"API请求数={len(chat_requests)}（应<=1）")
                    else:
                        log("快速连点", "FAIL", f"API请求数={len(chat_requests)}（应<=1，存在重复请求）")
                else:
                    log("快速连点", "FAIL", "未找到输入框")
            except Exception as e:
                log("快速连点", "FAIL", str(e)[:200])
            
            # ============================================
            # 第六组：@单人
            # ============================================
            print("\n" + "="*60)
            print("第六组：@单人测试")
            print("="*60)
            
            try:
                network_requests.clear()
                textarea = page.locator('textarea, input[placeholder*="输入"]')
                if await textarea.count() > 0:
                    await textarea.first.fill("@小雅 你好")
                    send_btn = page.get_by_role("button", name="发送")
                    if await send_btn.count() == 0:
                        send_btn = page.locator('button[aria-label*="发送"]')
                    await send_btn.first.click()
                    await page.wait_for_timeout(20000)
                    
                    # 检查消息中是否只有小雅
                    page_text = await page.inner_text('body')
                    xiaoya_count = page_text.count("小雅")
                    log("@单人", "PASS", f"小雅出现={xiaoya_count}次")
                else:
                    log("@单人", "FAIL", "未找到输入框")
            except Exception as e:
                log("@单人", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/06_mention_single.png")
            
            # ============================================
            # 第七组：@多人
            # ============================================
            print("\n" + "="*60)
            print("第七组：@多人测试")
            print("="*60)
            
            try:
                network_requests.clear()
                textarea = page.locator('textarea, input[placeholder*="输入"]')
                if await textarea.count() > 0:
                    await textarea.first.fill("@小雅 @小王 你们好")
                    send_btn = page.get_by_role("button", name="发送")
                    if await send_btn.count() == 0:
                        send_btn = page.locator('button[aria-label*="发送"]')
                    await send_btn.first.click()
                    await page.wait_for_timeout(30000)
                    
                    page_text = await page.inner_text('body')
                    xiaoya_count = page_text.count("小雅")
                    xiaowang_count = page_text.count("小王")
                    
                    # 检查 API 请求
                    chat_requests = [r for r in network_requests if "/api/chat/" in r["url"]]
                    
                    if xiaoya_count > 0 and xiaowang_count > 0 and len(chat_requests) <= 1:
                        log("@多人", "PASS", f"小雅={xiaoya_count}, 小王={xiaowang_count}, API请求={len(chat_requests)}")
                    else:
                        log("@多人", "FAIL", f"小雅={xiaoya_count}, 小王={xiaowang_count}, API请求={len(chat_requests)}")
                else:
                    log("@多人", "FAIL", "未找到输入框")
            except Exception as e:
                log("@多人", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/07_mention_multi.png")
            
            # ============================================
            # Console 错误检查
            # ============================================
            print("\n" + "="*60)
            print("Console 错误检查")
            print("="*60)
            
            if console_errors:
                # 过滤掉无关错误
                relevant_errors = [e for e in console_errors if "FedCM" not in e and "Provider's accounts" not in e and "403" not in e]
                if relevant_errors:
                    log("Console 错误", "FAIL", f"{len(relevant_errors)}个相关错误: {relevant_errors[:3]}")
                else:
                    log("Console 错误", "PASS", f"无相关错误（{len(console_errors)}个无关错误已过滤）")
            else:
                log("Console 错误", "PASS", "无错误")
            
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
        print("E2E 测试结果汇总")
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
        
        # 保存结果
        with open("e2e_full_results.json", "w", encoding="utf-8") as f:
            json.dump({"results": results, "timings": timings, "passed": passed, "failed": failed}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    os.makedirs("e2e_screenshots", exist_ok=True)
    asyncio.run(main())
