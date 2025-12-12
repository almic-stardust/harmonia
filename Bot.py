#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio

from Config_manager import Config
from Discord_manager import bot
import Discord_manager
import IRC_manager

@bot.event
async def on_ready():
	# Event triggered when the bot has connected to Discord
	print(f"[Discord] Logged in as {bot.user}")

async def Start_bot():
	IRC_manager.Instance = IRC_manager.Connection(
		nickname=Config["IRC"]["nick"],
		username=Config["IRC"]["username"],
		realname=Config["IRC"]["real_name"]
	)
	await IRC_manager.Instance.connect(
		hostname=Config["IRC"]["server"],
		tls=False,
		tls_verify=False
	)
	await bot.start(Config["Token"])
asyncio.run(Start_bot())
