#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio

from Config_manager import Config
import Discord_manager
import Commands_manager

async def main():
	await Discord_manager.Init_webhooks()
	await Discord_manager.bot.start(Config["Discord"]["Token"])

if __name__ == "__main__":
	asyncio.run(main())
