#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import time
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged

API_ID = int(os.environ.get("TG_API_ID", "0").strip())
API_HASH = os.environ.get("TG_API_HASH", "").strip()
SESSION_STRING = os.environ.get("TG_SESSION_STRING", "").strip()
PROXY_SERVER = os.environ.get("PROXY_SERVER", "").strip()

# ============ 必改配置 ============
# DNSHE 用户交流社区群组。
# 优先使用群组 username；如果群组没有公开 username，改为群组数字 ID（如 -1001234567890）
DNSHE_GROUP = os.environ.get("DNSHE_GROUP", "@HiaiFeng").strip()

# 要发送的签到命令
CHECKIN_COMMAND = "/checkin@DNSHEbot"

if not all([API_ID, API_HASH, SESSION_STRING]):
    print("❌ 缺少必要的环境变量：请设置 TG_API_ID, TG_API_HASH, TG_SESSION_STRING")
    sys.exit(1)

print(f"API_ID 长度: {len(str(API_ID))}, API_HASH 长度: {len(API_HASH)}")
print(f"SESSION_STRING 长度: {len(SESSION_STRING)} 字符")
print(f"🎯 目标群组: {DNSHE_GROUP}")

proxy = None
if PROXY_SERVER:
    parsed = urlparse(PROXY_SERVER)
    if parsed.scheme in ("http", "https"):
        proxy = ("http", parsed.hostname, parsed.port)
    elif parsed.scheme == "socks5":
        proxy = ("socks5", parsed.hostname, parsed.port)
    else:
        print(f"⚠️ 未知代理协议: {parsed.scheme}，忽略")
    if proxy:
        print(f"🔌 使用代理: {PROXY_SERVER}")

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    proxy=proxy,
    connection=ConnectionTcpAbridged,
)


async def main():
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("❌ 会话未授权。")
            sys.exit(1)
        print("✅ 会话授权检查通过")

        await client.start()
        me = await client.get_me()
        print(f"👤 登录用户: {me.first_name} (@{me.username or '无用户名'})")
    except Exception as e:
        print(f"❌ 登录失败: {e}")
        sys.exit(1)

    # 获取 DNSHE 用户交流社区群组
    try:
        group = await client.get_entity(DNSHE_GROUP)
        print(f"📌 找到群组: {getattr(group, 'title', DNSHE_GROUP)}")
    except Exception as e:
        print(f"❌ 无法获取群组 {DNSHE_GROUP}: {e}")
        print("如果群组是私有群，请把 DNSHE_GROUP 改为群组的数字 ID（如 -100xxxxxxxxxx）")
        sys.exit(1)

    send_time = time.time()
    await client.send_message(group, CHECKIN_COMMAND)
    print(f"📤 已在群组中发送: {CHECKIN_COMMAND}")

    print("⏳ 等待机器人回复...")
    timeout = 20
    reply_received = False
    while time.time() - send_time < timeout:
        messages = await client.get_messages(group, limit=10)
        for msg in messages:
            # 筛选：非自己发出、时间在发送命令之后、且来自 DNSHEbot 或包含签到关键词
            if msg.out:
                continue
            if msg.date.timestamp() < send_time:
                continue

            sender_username = ""
            if msg.sender:
                sender_username = getattr(msg.sender, "username", "") or ""

            text = msg.text or ""
            # DNSHEbot 的回复可能不带 username，用关键词兜底
            if (
                sender_username.lower() == "dnshebot"
                or "签到" in text
                or "积分" in text
                or "checkin" in text.lower()
            ):
                print(f"📩 机器人回复:\n{text}")
                reply_received = True
                break
        if reply_received:
            break
        await asyncio.sleep(1)

    if not reply_received:
        print("⏰ 超时未收到明确回复，签到命令已发送，可能已成功但未回复。")
        # 不强制 exit 1，因为很多签到机器人成功时静默或只更新积分

    await client.disconnect()
    print("🔒 连接已断开")


if __name__ == "__main__":
    asyncio.run(main())
