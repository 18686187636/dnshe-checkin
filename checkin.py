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
from telethon.tl.types import PeerChannel

# ================== 环境变量 ==================
API_ID_RAW = os.environ.get("TG_API_ID", "").strip()
API_HASH = os.environ.get("TG_API_HASH", "").strip()
SESSION_STRING = os.environ.get("TG_SESSION_STRING", "").strip()
PROXY_SERVER = os.environ.get("PROXY_SERVER", "").strip()

# DNSHE 用户交流社区私有群 ID，形如 -1003219886860
GROUP_ID_RAW = os.environ.get("DNSHE_GROUP_ID", "").strip()

# 签到命令
CHECKIN_COMMAND = "/checkin@DNSHEbot"

# ================== 参数校验 ==================
if not API_ID_RAW or not API_HASH or not SESSION_STRING:
    print("❌ 缺少必要的环境变量：请设置 TG_API_ID, TG_API_HASH, TG_SESSION_STRING")
    sys.exit(1)

try:
    API_ID = int(API_ID_RAW)
except ValueError:
    print(f"❌ TG_API_ID 不是合法整数: {API_ID_RAW!r}")
    sys.exit(1)

if not GROUP_ID_RAW:
    print("❌ 缺少环境变量 DNSHE_GROUP_ID，例如 -1003219886860")
    sys.exit(1)

try:
    DNSHE_GROUP_ID = int(GROUP_ID_RAW)
except ValueError:
    print(f"❌ DNSHE_GROUP_ID 不是合法整数: {GROUP_ID_RAW!r}")
    sys.exit(1)

print(f"API_ID 长度: {len(str(API_ID))}, API_HASH 长度: {len(API_HASH)}")
print(f"SESSION_STRING 长度: {len(SESSION_STRING)} 字符")
print(f"🎯 目标私有群 ID: {DNSHE_GROUP_ID}")
print(f"📝 签到命令: {CHECKIN_COMMAND}")

if len(SESSION_STRING) < 50:
    print("⚠️ SESSION_STRING 过短，可能无效")
    sys.exit(1)

# ================== 代理解析 ==================
proxy = None
if PROXY_SERVER:
    parsed = urlparse(PROXY_SERVER)
    if parsed.scheme in ("http", "https"):
        proxy = ("http", parsed.hostname, parsed.port)
    elif parsed.scheme == "socks5":
        proxy = ("socks5", parsed.hostname, parsed.port)
    else:
        print(f"⚠️ 未知代理协议: {parsed.scheme}，忽略代理")
    if proxy:
        print(f"🔌 使用代理: {PROXY_SERVER}")

# ================== 创建客户端 ==================
client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    proxy=proxy,
    connection=ConnectionTcpAbridged,
)


async def resolve_group(client, group_id):
    """
    解析私有群实体。
    优先用 PeerChannel 直接解析；
    失败时退化为扫描对话列表，按 dialog.id 匹配。
    """
    try:
        return await client.get_entity(PeerChannel(group_id))
    except Exception as e:
        print(f"⚠️ PeerChannel 直接解析失败: {e}")
        print("🔍 尝试扫描对话列表查找群组...")

    try:
        async for dialog in client.iter_dialogs():
            if dialog.id == group_id:
                print(f"✅ 在对话列表中找到群组: {dialog.name}")
                return dialog.entity
    except Exception as e:
        print(f"❌ 扫描对话列表失败: {e}")

    raise ValueError(
        f"无法定位群组 {group_id}。请确认：\n"
        f"  1. 账号已加入该私有群\n"
        f"  2. DNSHE_GROUP_ID 是否正确（应为 -100 开头的完整 ID）\n"
        f"  3. SESSION_STRING 是否来自同一个账号"
    )


async def main():
    # ---------- 登录 ----------
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("❌ 会话未授权。")
            print("可能原因：")
            print("  1. SESSION_STRING 已过期或无效")
            print("  2. API_ID / API_HASH 与生成 session 时不一致")
            print("  3. 代理未生效，导致无法验证授权")
            sys.exit(1)
        print("✅ 会话授权检查通过")

        await client.start()
        me = await client.get_me()
        print(f"👤 登录用户: {me.first_name} (@{me.username or '无用户名'})")
    except Exception as e:
        print(f"❌ 登录失败: {e}")
        sys.exit(1)

    # ---------- 定位私有群 ----------
    try:
        group = await resolve_group(client, DNSHE_GROUP_ID)
        print(f"📌 已定位群组: {getattr(group, 'title', DNSHE_GROUP_ID)}")
    except Exception as e:
        print(f"❌ 无法获取群组: {e}")
        sys.exit(1)

    # ---------- 发送签到命令 ----------
    send_time = time.time()
    try:
        sent_msg = await client.send_message(group, CHECKIN_COMMAND)
        print(f"📤 已在群组中发送: {CHECKIN_COMMAND}")
    except Exception as e:
        print(f"❌ 发送签到命令失败: {e}")
        sys.exit(1)

    # ---------- 等待机器人回复 ----------
    print("⏳ 等待机器人回复...")
    timeout = 20
    reply_received = False

    while time.time() - send_time < timeout:
        try:
            messages = await client.get_messages(group, limit=20)
        except Exception as e:
            print(f"⚠️ 获取群消息失败: {e}")
            messages = []

        for msg in messages:
            # 跳过自己发出的消息
            if msg.out:
                continue
            # 跳过发送命令之前的旧消息
            if msg.date.timestamp() < send_time:
                continue

            text = msg.text or ""
            sender_username = ""
            try:
                if msg.sender:
                    sender_username = (getattr(msg.sender, "username", "") or "").lower()
            except Exception:
                pass

            # 是否回复了我们发送的那条消息
            is_reply_to_us = (
                getattr(msg, "reply_to_msg_id", None) == sent_msg.id
            )

            # 匹配 DNSHEbot 或签到关键词
            keyword_hit = any(
                k in text
                for k in ("签到", "积分", "已签到", "checkin", "Checkin", "CHECKIN")
            )

            if sender_username == "dnshebot" or is_reply_to_us or keyword_hit:
                print("📩 机器人回复:")
                print(text)
                reply_received = True
                break

        if reply_received:
            break

        await asyncio.sleep(1)

    if not reply_received:
        print("⏰ 超时未收到明确回复。命令已发送，签到可能已成功但机器人未回复。")
        # 不强制 exit 1，避免 Actions 因机器人静默而误报失败

    await client.disconnect()
    print("🔒 连接已断开")


if __name__ == "__main__":
    asyncio.run(main())
