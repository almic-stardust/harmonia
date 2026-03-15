# -*- coding: utf-8 -*-

import random

from Discord_manager import bot
import Discord_manager
import IRC_manager

def Roll_dices(Dices):
	Rolls, Limit = map(int, Dices.split("d"))
	return ", ".join(str(random.randint(1, Limit)) for _ in range(Rolls))

@bot.command()
async def roll(Context, Dices: str):
	"""Roll dices in NdN format"""
	IRC_chan = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)["irc_chan"]
	if IRC_chan:
		Author = Context.author.display_name
		await IRC_manager.Instance.Relay_Discord_message(IRC_chan, Author, f"!roll {Dices}")
	try:
		Rolls = Roll_dices(Dices)
	except Exception:
		await Context.send("Format has to be in NdN.")
		if IRC_chan:
			await IRC_manager.Instance.message(IRC_chan, "Format has to be NdN.")
		return
	await Context.send(Rolls)
	if IRC_chan:
		await IRC_manager.Instance.message(IRC_chan, Rolls)

async def roll_from_irc(Bridge, Message):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	try:
		Dices = Message.split()[1]
		Rolls = Roll_dices(Dices)
	except Exception:
		await IRC_manager.Instance.message(IRC_chan, "Format has to be NdN.")
		await Discord_chan.send("Format has to be NdN.")
		return
	await IRC_manager.Instance.message(IRC_chan, Rolls)
	await Discord_chan.send(Rolls)
