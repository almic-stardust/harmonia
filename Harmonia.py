#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio

from Config_manager import Config
import Discord_manager
from Discord_manager import bot
from Discord_manager import Reconcile_downloaded_files
import Commands_manager

IRC_enabled = Config["enabled_sections"]["irc"]
if IRC_enabled:
	import IRC_manager
	from Discord_manager import Delete_expired_IRC_messages_from_Discord
	IRC_task = None
History_enabled = Config["enabled_sections"]["history"]
Users_enabled = Config["enabled_sections"]["users"]

###############################################################################
# Discord events
###############################################################################

# Event triggered when the bot has connected to Discord
@bot.event
async def on_ready():
	# Ensure async errors are visible (by default, discord.py silently drop task errors)
	Loop = asyncio.get_running_loop()
	Loop.set_exception_handler(lambda loop, context: print("ASYNC ERROR:", context))
	if len(bot.guilds) == 0:
		print("[Discord] Bot is not yet in any server.")
		await Stop_bot()
		return
	print(f"[Discord] Logged in as {bot.user}")
	if IRC_enabled:
		global IRC_task
		# Start IRC loop only once
		if IRC_task is None or IRC_task.done():
			IRC_task = asyncio.create_task(IRC_manager.Run_IRC_loop())
	# Start background tasks
	if IRC_enabled:
		if not Delete_expired_IRC_messages_from_Discord.is_running():
			if History_enabled and Users_enabled:
				Delete_expired_IRC_messages_from_Discord.start()
	if not Reconcile_downloaded_files.is_running():
		if History_enabled:
			Reconcile_downloaded_files.start()

###############################################################################
# Shutdown
###############################################################################

async def Stop_bot():
	print("Shutdown initiated…")
	# Stop IRC loop
	if IRC_enabled:
		global IRC_task
		IRC_manager.IRC_shutting_down.set()
		# Disconnect from IRC
		IRC_instance = IRC_manager.Get_instance()
		if IRC_instance:
			try:
				await IRC_instance.Shutdown_IRC()
			except Exception as Error:
				print(f"[IRC] Error during shutdown: {Error}")
		# Wait for the IRC loop to exit cleanly
		if IRC_task:
			try:
				await IRC_task
			except Exception as Error:
				print(f"[IRC] Error during task loop exit: {Error}")
	# Stop Discord
	await Discord_manager.Shutdown_Discord()
	print("Shutdown complete.")

###############################################################################
# Entry point: start the bot
###############################################################################

async def main():
	await Discord_manager.Init_webhooks()
	await bot.start(Config["discord"]["token"])

if __name__ == "__main__":
	asyncio.run(main())
