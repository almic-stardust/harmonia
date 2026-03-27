# -*- coding: utf-8 -*-

import random
import re
import hashlib

from Discord_manager import bot
import Discord_manager
import IRC_manager

global Straws_bag
Straws_bag = {}

async def No_help_for_IRC(Bridge):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	await IRC_manager.Get_instance().message(IRC_chan,
			"The !help command is only available on Discord."
	)
	await Discord_chan.send("The !help command is only available on Discord.")

def Roll_dices(Dices):
	Rolls, Limit = map(int, Dices.split("d"))
	return ", ".join(str(random.randint(1, Limit)) for _ in range(Rolls))

@bot.command()
async def roll(Context, Dices: str):
	"""Roll dices in NdN format"""
	# If the Discord chan is bridged to an IRC chan, relay on IRC the command sent on Discord
	IRC_chan = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)["irc_chan"]
	if IRC_chan:
		Author = Context.author.display_name
		await IRC_manager.Get_instance().Relay_Discord_message(IRC_chan, Author, f"!roll {Dices}")
	try:
		Rolls = Roll_dices(Dices)
	except Exception:
		await Context.send("Format has to be in NdN.")
		if IRC_chan:
			await IRC_manager.Get_instance().message(IRC_chan, "Format has to be NdN.")
		return
	await Context.send(Rolls)
	if IRC_chan:
		await IRC_manager.Get_instance().message(IRC_chan, Rolls)

async def IRC_roll(Bridge, Dices):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	try:
		Rolls = Roll_dices(Dices)
	except Exception:
		await IRC_manager.Get_instance().message(IRC_chan, "Format has to be NdN.")
		await Discord_chan.send("Format has to be NdN.")
		return
	await IRC_manager.Get_instance().message(IRC_chan, Rolls)
	await Discord_chan.send(Rolls)

def Show_bag():
	global Straws_bag
	if len(Straws_bag) > 0:
		Bag_content = "The bag contains the following straws:"
		for User in Straws_bag.keys():
			Bag_content += f"\n[{User}] {Straws_bag[User]}"
	else:
		Bag_content = "The bag is currently empty. See “!help straws” (on Discord)"
	return Bag_content

@bot.group()
async def straws(Context):
	"""Draw straws among a group, with a reproducible pseudo-randomness."""
	# If no subcommand is invoked, show what’s currently in the bag
	if not Context.invoked_subcommand:
		Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
		if Bridge:
			IRC_chan = Bridge["irc_chan"]
			Author = Context.author.display_name
			# Relay on IRC the command sent on Discord
			await IRC_manager.Get_instance().Relay_Discord_message(IRC_chan, Author, "!straws")
			Bag_content = Show_bag()
			await Context.send(Bag_content)
			await IRC_manager.Get_instance().message(IRC_chan, Bag_content)

async def IRC_straws(Bridge):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	Bag_content = Show_bag()
	await Discord_chan.send(Bag_content)
	await IRC_manager.Get_instance().message(IRC_chan, Bag_content)

@straws.command(name="help")
async def Straws_help(Context):
	IRC_chan = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)["irc_chan"]
	if IRC_chan:
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.Get_instance().Relay_Discord_message(IRC_chan, Author, "!straws help")
	await Context.send("See “!help straws”.")
	if IRC_chan:
		await IRC_manager.Get_instance().message(IRC_chan, "See “!help straws” (on Discord).")

async def IRC_straws_help(Bridge):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	await IRC_manager.Get_instance().message(IRC_chan, "See “!help straws” (on Discord).")
	await Discord_chan.send("See “!help straws”.")

def Add_straw(Author, Straw):
	global Straws_bag
	# Remove spaces, tabs and newlines (ASCII)
	Straw = "".join(Straw.split())
	# Remove Unicode whitespaces
	Straw = re.sub(r"\s+", "", Straw, flags=re.UNICODE)
	# Remove dots, commas and underscores
	Straw = Straw.replace(".", "").replace(",", "").replace("_", "")
	# Capitalize the first letter, and convert the following 27 letters to lowercase
	Straw = Straw[0].upper() + Straw[1:27].lower()
	Straws_bag.update({Author: Straw})
	return Straw

@straws.command(name="add")
async def Straws_add(Context, Word: str):
	"""Put a straw in the bag, to participate in the draw."""
	# A straw is made up of a word, that will be capitalized and concatenated to 27 letters
	# (27 because intergouvernementalisations)
	Author = Context.author.display_name
	# Relay on IRC the command sent on Discord
	IRC_chan = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)["irc_chan"]
	if IRC_chan:
		await IRC_manager.Get_instance().Relay_Discord_message(IRC_chan, Author,
				f"!straws add {Word}"
		)
	try:
		Straw = Add_straw(Author, Word)
	except Exception:
		await Context.send("Your straw couldn’t be added in the bag!")
		if IRC_chan:
			await IRC_manager.Get_instance().message(IRC_chan,
					"Your straw couldn’t be added in the bag!"
			)
		return
	# Confirmation via DM on Discord
	await Context.author.send(f"Your straw “{Straw}” has been added in the bag.")

async def IRC_straws_add(Bridge, Author, Word):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	if not Word:
		await IRC_manager.Get_instance().message(IRC_chan, "Usage: !straws add word")
		await Discord_chan.send("Usage: !straws add word")
		return
	try:
		Straw = Add_straw(Author, Word)
	except Exception:
		await IRC_manager.Get_instance().message(IRC_chan,
				"Your straw couldn’t be added in the bag!"
		)
		await Discord_chan.send("Your straw couldn’t be added in the bag!")
		return
	# Confirmation via PM on IRC
	await IRC_manager.Get_instance().message(Author,
			f"Your straw “{Straw}” has been added in the bag."
	)

async def Draw_a_straw(Bridge):
	global Straws_bag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	try:
		# Simulate a random seed, by concatenating the words given by the users
		Common_key = ""
		Users = []
		for User in Straws_bag.keys():
			Common_key += Straws_bag[User]
			Users.append(User)
		# Create a dedicated key for each user, by appending their name to the common key, and then
		# calculate a hash for each user’s key
		def Calculate_hash(User):
		    return hashlib.sha256((Common_key + User).encode("utf8")).hexdigest()
		Users.sort(key=Calculate_hash)
	except Exception:
		await Discord_chan.send("It’s not possible to draw a straw!")
		await IRC_manager.Get_instance().message(IRC_chan, "It’s not possible to draw a straw!")
		return
	# The user with the smallest hash (the first place in the list) drew the short straw
	Lucky_one = Users[0]
	Reply = Show_bag()
	Reply += f"\nThe common key is: {Common_key}\n\n"
	Reply += f"And {Lucky_one} is the lucky (?) one who pulls the shortest straw."
	await Discord_chan.send(Reply)
	await IRC_manager.Get_instance().message(IRC_chan, Reply)

@straws.command(name="draw")
async def Straws_draw(Context):
	"""Pull a straw from the bag."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.Get_instance().Relay_Discord_message(IRC_chan, Author, "!straws draw")
		await Draw_a_straw(Bridge)

async def IRC_straws_draw(Bridge):
	await Draw_a_straw(Bridge)

@straws.command(name="empty")
async def Straws_empty(Context):
	"""Empty the bag of straws (reset the pool)."""
	global Straws_bag
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.Get_instance().Relay_Discord_message(IRC_chan, Author, "!straws empty")
		Straws_bag = {}
		Reply = "The bag is now empty."
		await Context.send(Reply)
		await IRC_manager.Get_instance().message(IRC_chan, Reply)

async def IRC_straws_empty(Bridge):
	global Straws_bag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	Straws_bag = {}
	Reply = "The bag is now empty."
	await IRC_manager.Get_instance().message(IRC_chan, Reply)
	await Discord_chan.send(Reply)
