#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio

from Config_manager import Config
from Discord_manager import bot
import Discord_manager
import IRC_manager

###############################################################################
# Starting the bot
###############################################################################

# Event triggered when the bot has connected to Discord
@bot.event
async def on_ready():
	if len(bot.guilds) == 0:
		print("[Discord] Bot is not yet in any server.")
		await Discord_manager.Stop_bot(IRC_manager.Instance)
		return
	print(f"[Discord] Logged in as {bot.user}")

async def Start_bot():
	IRC_manager.Instance = IRC_manager.Connection(
		nickname=Config["irc"]["nick"],
		username=Config["irc"]["username"],
		realname=Config["irc"]["real_name"]
	)
	await IRC_manager.Instance.connect(
		hostname=Config["irc"]["server"],
		tls=True,
		tls_verify=False
	)
	await bot.start(Config["discord"]["token"])
asyncio.run(Start_bot())
