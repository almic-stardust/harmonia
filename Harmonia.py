#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio

from Config_manager import Config
from Discord_manager import bot
import Discord_manager
from Discord_manager import Reconcile_downloaded_files
from Discord_manager import Delete_expired_messages
import IRC_manager
import Commands_manager

###############################################################################
# Starting the bot
###############################################################################

# Event triggered when the bot has connected to Discord
@bot.event
async def on_ready():
	# By default, discord.py silently drop task errors
	Loop = asyncio.get_running_loop()
	Loop.set_exception_handler(lambda loop, context: print("ASYNC ERROR:", context))
	if len(bot.guilds) == 0:
		print("[Discord] Bot is not yet in any server.")
		await Discord_manager.Stop_bot(IRC_manager.Get_instance())
		return
	# Tasks
	if not Delete_expired_messages.is_running():
		Delete_expired_messages.start()
	if not Reconcile_downloaded_files.is_running():
		Reconcile_downloaded_files.start()
	print(f"[Discord] Logged in as {bot.user}")

async def Start_bot():
	IRC_instance = IRC_manager.Connection_handler(
		nickname=Config["irc_info"]["nick"],
		username=Config["irc_info"]["username"],
		realname=Config["irc_info"]["real_name"]
	)
	await IRC_instance.connect(
		hostname=Config["irc_info"]["server"],
		tls=True, tls_verify=False
	)
	await Discord_manager.Init_webhooks()
	await bot.start(Config["discord"]["token"])
asyncio.run(Start_bot())
