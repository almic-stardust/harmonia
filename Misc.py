# -*- coding: utf-8 -*-

import random

from Discord_manager import bot

@bot.command()
async def roll(Context, Dice: str):
	"""Roll a dice in NdN format"""
	try:
		Rolls, Limit = map(int, Dice.split("d"))
	except Exception:
		await Context.send("Format has to be in NdN.")
		return
	Result = ", ".join(str(random.randint(1, Limit)) for r in range(Rolls))
	await Context.send(Result)
