#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio

from Config_manager import Config
import Discord_manager
import Commands_manager

async def main():
	await Discord_manager.Init_webhooks()
	Bot_task = asyncio.create_task(Discord_manager.bot.start(Config["Discord"]["Token"]))
	Shutdown_task = asyncio.create_task(Commands_manager.Request_shutdown.wait())
	try:
		from Gears import Wait_for_events
		await Wait_for_events(Bot_task, Shutdown_task)
	finally:
		Shutdown_task.cancel()
		await asyncio.gather(Shutdown_task, return_exceptions=True)
		from Gears import Stop_bot
		await Stop_bot()
	# Re-raise any exception from bot.start()
	await Bot_task

if __name__ == "__main__":
	asyncio.run(main())
