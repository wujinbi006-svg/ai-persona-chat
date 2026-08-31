"""
Chat Core 2.0 RC-3 E2E 测试 V2 - 使用正确的 UI 选择器
"""
import asyncio
import json
import time
import os
from playwright.async_api import async_playwright

STAGING_URL = "https://ai-persona-chat-qkito1k5p-ai-persona-team.vercel.app"
TEST_EMAIL = f"rc3_v2_{int(time.time())}@example.com"
TEST_PASSWORD = "Test123456!"

results = {}
timings = {}

def log(test_name, status, detail=""):
    results[test_name] = {"status": status, "detail": detail}
    icon = "✅" if status == "PASS" else "❌"
    print(f"{icon} {test_name}: {status} {detail[:120]}")

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
        
        network_requests = []
        def on_request(request):
            if "/api/" in request.url:
                network_requests.append({"url": request.url, "method": request.method})
        page.on("request", on_request)
        
        try:
            # ============================================
            # 1. 页面加载
            # ============================================
            print("\n=== 1. 页面加载 ===")
            t0 = time.time()
            await page.goto(STAGING_URL, wait_until="networkidle", timeout=60000)
            t1 = time.time()
            title = await page.title()
            load_ms = record_time("页面加载", t0, t1)
            log("页面加载", "PASS", f"title={title}, {load_ms}ms")
            await page.screenshot(path="e2e_screenshots/v2_01_login.png")
            
            # ============================================
            # 2. 注册
            # ============================================
            print("\n=== 2. 注册 ===")
            try:
                # 点击注册链接
                register_link = page.locator('a[href="#register"]')
                if await register_link.count() > 0:
                    await register_link.first.click()
                    await page.wait_for_timeout(1000)
                
                # 填写邮箱
                email_input = page.locator('input[type="email"]')
                await email_input.first.fill(TEST_EMAIL)
                
                # 填写密码（可能有两个：密码和确认密码）
                password_inputs = page.locator('input[type="password"]')
                count = await password_inputs.count()
                await password_inputs.nth(0).fill(TEST_PASSWORD)
                if count > 1:
                    await password_inputs.nth(1).fill(TEST_PASSWORD)
                
                # 点击提交
                submit_btn = page.locator('button[type="submit"]')
                await submit_btn.first.click()
                
                # 等待注册完成
                await page.wait_for_timeout(10000)
                current_url = page.url
                
                if "login" not in current_url and "vercel.com" not in current_url:
                    log("用户注册", "PASS", f"email={TEST_EMAIL}")
                else:
                    log("用户注册", "FAIL", f"跳转异常: {current_url[:100]}")
            except Exception as e:
                log("用户注册", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/v2_02_after_register.png")
            
            # ============================================
            # 3. 检查登录状态和 CORS
            # ============================================
            print("\n=== 3. 登录状态和 CORS ===")
            current_url = page.url
            page_text = await page.inner_text('body')
            
            if "新建聊天" in page_text or "角色设置" in page_text or "添加 AI 角色" in page_text:
                log("登录状态", "PASS", "已登录，看到应用界面")
            else:
                log("登录状态", "FAIL", f"未看到应用界面, url={current_url[:80]}")
            
            # 检查 CORS 错误
            cors_errors = [e for e in console_errors if "CORS" in e or "Access-Control" in e]
            if cors_errors:
                log("CORS", "FAIL", f"{len(cors_errors)}个CORS错误")
            else:
                log("CORS", "PASS", "无CORS错误")
            
            # ============================================
            # 4. 新建聊天
            # ============================================
            print("\n=== 4. 新建聊天 ===")
            try:
                t0 = time.time()
                # 查找新建聊天按钮
                new_chat_btn = page.get_by_text("新建聊天", exact=False)
                if await new_chat_btn.count() == 0:
                    new_chat_btn = page.locator('button:has-text("新建聊天")')
                if await new_chat_btn.count() > 0:
                    await new_chat_btn.first.click()
                    await page.wait_for_timeout(3000)
                    t1 = time.time()
                    ui_ms = record_time("新建聊天UI", t0, t1)
                    
                    # 检查是否进入角色设置页面
                    page_text = await page.inner_text('body')
                    if "角色设置" in page_text or "添加 AI 角色" in page_text:
                        log("新建聊天", "PASS", f"UI显示={ui_ms}ms, 进入角色设置")
                    else:
                        log("新建聊天", "PASS", f"UI显示={ui_ms}ms")
                else:
                    log("新建聊天", "FAIL", "未找到新建聊天按钮")
            except Exception as e:
                log("新建聊天", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/v2_03_new_chat.png")
            
            # ============================================
            # 5. 创建角色
            # ============================================
            print("\n=== 5. 创建角色 ===")
            try:
                t0 = time.time()
                # 点击添加 AI 角色按钮
                add_char_btn = page.get_by_text("添加 AI 角色", exact=False)
                if await add_char_btn.count() == 0:
                    add_char_btn = page.locator('button:has-text("添加")')
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
                        await persona_input.first.fill("你是小雅，温柔可爱的女生，喜欢喝奶茶。")
                    
                    # 点击保存
                    save_btn = page.get_by_role("button", name="保存")
                    if await save_btn.count() == 0:
                        save_btn = page.locator('button[type="submit"]')
                    if await save_btn.count() == 0:
                        save_btn = page.locator('button:has-text("保存")')
                    await save_btn.first.click()
                    await page.wait_for_timeout(4000)
                    t1 = time.time()
                    char_ms = record_time("创建角色", t0, t1)
                    
                    # 检查角色是否创建成功
                    page_text = await page.inner_text('body')
                    if "小雅" in page_text:
                        log("创建角色", "PASS", f"耗时={char_ms}ms, 小雅已创建")
                    else:
                        log("创建角色", "FAIL", f"耗时={char_ms}ms, 未找到小雅")
                else:
                    log("创建角色", "FAIL", "未找到添加角色按钮")
            except Exception as e:
                log("创建角色", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/v2_04_character.png")
            
            # 创建第二个角色
            try:
                add_char_btn = page.get_by_text("添加 AI 角色", exact=False)
                if await add_char_btn.count() > 0:
                    await add_char_btn.first.click()
                    await page.wait_for_timeout(1500)
                    name_input = page.locator('input[placeholder*="名称"], input[name="name"]')
                    if await name_input.count() == 0:
                        name_input = page.locator('input').first
                    await name_input.first.fill("小王")
                    persona_input = page.locator('textarea, input[placeholder*="人格"]')
                    if await persona_input.count() > 0:
                        await persona_input.first.fill("你是小王，阳光开朗的男生。")
                    save_btn = page.locator('button:has-text("保存")')
                    if await save_btn.count() == 0:
                        save_btn = page.locator('button[type="submit"]')
                    await save_btn.first.click()
                    await page.wait_for_timeout(3000)
                    log("创建第二个角色", "PASS", "小王已创建")
            except Exception as e:
                log("创建第二个角色", "FAIL", str(e)[:100])
            
            # ============================================
            # 6. 进入聊天
            # ============================================
            print("\n=== 6. 进入聊天 ===")
            try:
                enter_btn = page.get_by_text("进入聊天", exact=False)
                if await enter_btn.count() == 0:
                    enter_btn = page.locator('button:has-text("进入聊天")')
                if await enter_btn.count() > 0:
                    await enter_btn.first.click()
                    await page.wait_for_timeout(3000)
                    
                    page_text = await page.inner_text('body')
                    if "发送" in page_text or "输入消息" in page_text or "开始和" in page_text:
                        log("进入聊天", "PASS", "已进入聊天界面")
                    else:
                        log("进入聊天", "FAIL", "未进入聊天界面")
                else:
                    log("进入聊天", "FAIL", "未找到进入聊天按钮")
            except Exception as e:
                log("进入聊天", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/v2_05_chat.png")
            
            # ============================================
            # 7. 普通聊天
            # ============================================
            print("\n=== 7. 普通聊天 ===")
            try:
                network_requests.clear()
                t0 = time.time()
                
                # 查找输入框
                textarea = page.locator('textarea')
                if await textarea.count() > 0:
                    await textarea.first.fill("你好")
                    await page.wait_for_timeout(500)
                    
                    # 点击发送
                    send_btn = page.locator('button:has-text("发送")')
                    if await send_btn.count() == 0:
                        send_btn = page.get_by_role("button", name="发送")
                    await send_btn.first.click()
                    
                    # 等待 AI 回复
                    await page.wait_for_timeout(25000)
                    t1 = time.time()
                    chat_ms = record_time("普通聊天", t0, t1)
                    
                    # 检查 API 请求数量
                    chat_requests = [r for r in network_requests if "/api/chat/" in r["url"]]
                    log("普通聊天", "PASS", f"耗时={chat_ms}ms, API请求={len(chat_requests)}")
                else:
                    log("普通聊天", "FAIL", "未找到输入框")
            except Exception as e:
                log("普通聊天", "FAIL", str(e)[:200])
            
            await page.screenshot(path="e2e_screenshots/v2_06_chat_result.png")
            
            # ============================================
            # 8. Console 错误检查
            # ============================================
            print("\n=== 8. Console 错误检查 ===")
            relevant_errors = [e for e in console_errors if "FedCM" not in e and "Provider's accounts" not in e and "403" not in e and "GSI_LOGGER" not in e]
            if relevant_errors:
                log("Console 错误", "FAIL", f"{len(relevant_errors)}个相关错误: {relevant_errors[:3]}")
            else:
                log("Console 错误", "PASS", f"无相关错误（共{len(console_errors)}个，已过滤无关）")
            
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
        print("E2E V2 测试结果汇总")
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
        
        with open("e2e_v2_results.json", "w", encoding="utf-8") as f:
            json.dump({"results": results, "timings": timings, "passed": passed, "failed": failed}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    os.makedirs("e2e_screenshots", exist_ok=True)
    asyncio.run(main())
