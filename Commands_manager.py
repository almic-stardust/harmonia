# -*- coding: utf-8 -*-

import random
import re
import hashlib

from Discord_manager import bot
import Discord_manager
import IRC_manager

Straws_bag = {}
Ergobag = {}
Ergobag["Common_key"] = {}
Ergobag["Users"] = []

async def No_help_for_IRC(Bridge):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	await IRC_manager.GCI().Safe_message(IRC_chan,
			"The !help command is only available on Discord."
	)
	await Discord_chan.send("The !help command is only available on Discord.")

###############################################################################
# Roll dices
###############################################################################

def Roll_dices(Dices):
	Rolls, Limit = map(int, Dices.split("d"))
	Results = []
	for _ in range(Rolls):
		Roll = random.randint(1, Limit)
		Results.append(str(Roll))
	return ", ".join(Results)

@bot.command()
async def roll(Context, Dices: str):
	"""Roll dices in NdN format"""
	# If the Discord chan is bridged to an IRC chan, relay on IRC the command sent on Discord
	IRC_chan = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)["irc_chan"]
	if IRC_chan:
		Author = Context.author.display_name
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, f"!roll {Dices}")
	try:
		Rolls = Roll_dices(Dices)
	except Exception:
		await Context.send("Format has to be in NdN.")
		if IRC_chan:
			await IRC_manager.GCI().Safe_message(IRC_chan, "Format has to be NdN.")
		return
	await Context.send(Rolls)
	if IRC_chan:
		await IRC_manager.GCI().Safe_message(IRC_chan, Rolls)

async def IRC_roll(Bridge, Text):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	Parts = Text.split(maxsplit=1)
	if len(Parts) < 2:
		await IRC_manager.GCI().Safe_message(IRC_chan, "Usage: !roll NdN")
		await Discord_chan.send("Usage: !roll NdN")
		return
	Dices = Parts[1].lower()
	try:
		Rolls = Roll_dices(Dices)
	except Exception:
		await IRC_manager.GCI().Safe_message(IRC_chan, "Format has to be NdN.")
		await Discord_chan.send("Format has to be NdN.")
		return
	await IRC_manager.GCI().Safe_message(IRC_chan, Rolls)
	await Discord_chan.send(Rolls)

###############################################################################
# Draw straws
###############################################################################

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
			await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!straws")
			Bag_content = Show_bag()
			await Context.send(Bag_content)
			await IRC_manager.GCI().Safe_message(IRC_chan, Bag_content)

async def IRC_straws(Bridge):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	Bag_content = Show_bag()
	await Discord_chan.send(Bag_content)
	await IRC_manager.GCI().Safe_message(IRC_chan, Bag_content)

@straws.command(name="help")
async def Straws_help(Context):
	IRC_chan = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)["irc_chan"]
	if IRC_chan:
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!straws help")
	await Context.send("See “!help straws”.")
	if IRC_chan:
		await IRC_manager.GCI().Safe_message(IRC_chan, "See “!help straws” (on Discord).")

async def IRC_straws_help(Bridge):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	await IRC_manager.GCI().Safe_message(IRC_chan, "See “!help straws” (on Discord).")
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
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, f"!straws add {Word}")
	try:
		Straw = Add_straw(Author, Word)
	except Exception:
		await Context.send("Your straw couldn’t be added in the bag!")
		if IRC_chan:
			await IRC_manager.GCI().Safe_message(IRC_chan,
					"Your straw couldn’t be added in the bag!"
			)
		return
	# Confirmation via DM on Discord
	await Context.author.send(f"Your straw “{Straw}” has been added in the bag.")

async def IRC_straws_add(Bridge, Author, Text):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	# Retrieve arguments in one string, starting from the 2nd (after add)
	Word = "".join(Text.split()[2:])
	if not Word:
		await IRC_manager.GCI().Safe_message(IRC_chan, "Usage: !straws add word")
		await Discord_chan.send("Usage: !straws add word")
		return
	try:
		Straw = Add_straw(Author, Word)
	except Exception:
		await IRC_manager.GCI().Safe_message(IRC_chan, "Your straw couldn’t be added in the bag!")
		await Discord_chan.send("Your straw couldn’t be added in the bag!")
		return
	# Confirmation via query on IRC
	await IRC_manager.GCI().Safe_message(Author, f"Your straw “{Straw}” has been added in the bag.")

async def Draw_a_straw(Bridge):
	global Straws_bag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	if not Straws_bag:
		await Discord_chan.send("No straws to draw from.")
		await IRC_manager.GCI().Safe_message(IRC_chan, "No straws to draw from.")
		return
	# Simulate a random seed, by concatenating the words given by the users
	Common_key = " ".join(Straws_bag.values())
	Users = list(Straws_bag.keys())
	# Create a dedicated key for each user, by appending their name to the common key, and then
	# calculate a hash for each user’s key
	def Calculate_hash(User):
		return hashlib.sha256((Common_key + User).encode("utf8")).hexdigest()
	Users.sort(key=Calculate_hash)
	Reply = Show_bag()
	Reply += f"\nThe common key is: “{Common_key}”\n\n"
	# The user with the smallest hash (the first place in the list) drew the short straw
	Reply += f"And {Users[0]} is the lucky (?) one who pulls the shortest straw."
	await Discord_chan.send(Reply)
	await IRC_manager.GCI().Safe_message(IRC_chan, Reply)

@straws.command(name="draw")
async def Straws_draw(Context):
	"""Pull a straw from the bag."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!straws draw")
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
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!straws empty")
		Straws_bag = {}
		Reply = "The bag is now empty."
		await Context.send(Reply)
		await IRC_manager.GCI().Safe_message(IRC_chan, Reply)

async def IRC_straws_empty(Bridge):
	global Straws_bag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	Straws_bag = {}
	Reply = "The bag is now empty."
	await IRC_manager.GCI().Safe_message(IRC_chan, Reply)
	await Discord_chan.send(Reply)

###############################################################################
# Ergostraws
###############################################################################

async def Show_ergobag(Bridge):
	global Ergobag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	if len(Ergobag["Common_key"]) > 0:
		Bag_content = "The following users gave the following words:\n"
		for Author in Ergobag["Common_key"].keys():
			Bag_content += f"[{Author}] {Ergobag["Common_key"][Author]}\n"
		await Discord_chan.send(Bag_content)
		await IRC_manager.GCI().Safe_message(IRC_chan, Bag_content)
	else:
		Output = "The bag is currently empty. See “!help ergostraws"
		await Discord_chan.send(Output + "”.")
		await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")

@bot.group()
async def ergostraws(Context):
	# If no subcommand is invoked, show what’s currently in the bag
	if not Context.invoked_subcommand:
		Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
		if Bridge:
			IRC_chan = Bridge["irc_chan"]
			Author = Context.author.display_name
			# Relay on IRC the command sent on Discord
			await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!ergostraws")
			await Show_ergobag(Bridge)

async def IRC_ergostraws(Bridge):
	await Show_ergobag(Bridge)

@ergostraws.command(name="help")
async def Discord_ergostraws_help(Context):
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!ergostraws help")
		await Ergostraws_help(Bridge)
		await Discord_chan.send("See “!help ergostraws”.")
		await IRC_manager.GCI().Safe_message(IRC_chan, "See “!help ergostraws” (on Discord).")

async def IRC_ergostraws_help(Bridge):
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	await Discord_chan.send("See “!help ergostraws”.")
	await IRC_manager.GCI().Safe_message(IRC_chan, "See “!help ergostraws” (on Discord).")

async def Ergostraws_add(Bridge, Author, Straw, Context=None):
	global Ergobag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	try:
		# Remove dots, commas and underscores
		Straw = Straw.replace(".", " ").replace(",", " ").replace("_", " ")
		# Remove Unicode whitespaces
		Straw = re.sub(r"\s+", " ", Straw, flags=re.UNICODE)
		# Remove spaces, tabs and newlines (ASCII)
		Straw = Straw.split()
		# Capitalize the straw, or the different words constituting the straw
		Straw = "".join(Word.capitalize() for Word in Straw)
		# Ward off clever ones
		Straw = Straw[:30]
		Ergobag["Common_key"].update({Author: Straw})
	except Exception as Error:
		print(f"[Commands] Ergostraws_add(): {Error}")
		Output = "Your straw couldn’t be added in the bag!"
		await Discord_chan.send(Output)
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
		return
	Output = f"Your straw “{Straw}” has been added in the bag."
	# The command comes from Discord, confirmation via DM
	if Context:
		await Context.author.send(Output)
	# The command comes from IRC, confirmation via query
	else:
		await IRC_manager.GCI().Safe_message(Author, Output)

@ergostraws.command(name="add")
async def Discord_ergostraws_add(Context, Word: str):
	"""Put a straw in the bag."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, f"!ergostraws add {Word}")
		await Ergostraws_add(Bridge, Author, Word, Context)

async def IRC_ergostraws_add(Bridge, Author, Straw):
	if not Straw:
		Output = "Usage: !ergostraws add Word"
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
		await Discord_chan.send(Output)
		return
	Straw = Straw.split()
	# Remove “!ergostraws” and “add” from the splitted string
	Straw = Straw[2:]
	# Reform the string for processing in Ergostraws_add()
	Straw = " ".join(Straw)
	await Ergostraws_add(Bridge, Author, Straw)

async def Ergostraws_users(Bridge, Users):
	global Ergobag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	try:
		Users = Users.split()
		# Remove “!ergostraws” and “users” from the splitted string
		Users = Users[2:]
	except Exception as Error:
		print(f"[Commands] Users_ergostraw(): {Error}")
		await IRC_manager.GCI().Safe_message(IRC_chan, "No users provided!")
		await Discord_chan.send("No users provided!")
		return
	Ergobag["Users"] = Users
	Output = "The list of users has been set."
	await IRC_manager.GCI().Safe_message(IRC_chan, Output)
	await Discord_chan.send(Output)

@ergostraws.command(name="users")
async def Discord_ergostraws_users(Context, Users: str):
	"""Set the list of users between whom to draw."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!ergostraws users {Users}")
		await Ergostraws_users(Bridge, Users)

async def IRC_ergostraws_users(Bridge, Users):
	if not Users:
		Output = "Usage: !ergostraws users User1 User2 …"
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
		await Discord_chan.send(Output)
		return
	await Ergostraws_users(Bridge, Users)

async def Ergostraws_draw(Bridge):
	global Ergobag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	if len(Ergobag["Common_key"]) == 0:
		Output = "No straws to draw from. See “!help ergostraws"
		await Discord_chan.send(Output + "”.")
		await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")
		return
	if len(Ergobag["Users"]) == 0:
		Output = "No participants between whom to draw. See “!help ergostraws"
		await Discord_chan.send(Output + "”.")
		await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")
		return
	Common_key = " ".join(Ergobag["Common_key"].values())
	Hashes = {}
	for User in Ergobag["Users"]:
		# Create a dedicated key for each user, by appending their name to the common key, and then
		# calculate a hash for each user’s key
		Hash = hashlib.sha256((Common_key + User).encode("utf8")).hexdigest()
		Hashes[User] = Hash
	# Sort the list from smallest to biggest hash
	Users = Ergobag["Users"]
	Users.sort(key=lambda User: Hashes[User])
	print("Users = ", Users)
	Output = "The participants between whom to draw are: "
	Output += ", ".join(Ergobag["Users"]) + ".\n\n"
	Output += f"The common key is: “{Common_key}”.\n"
	Output += "Hash for each participant:\n"
	for User in Ergobag["Users"]:
		Output += f"[{User}] {Hashes[User]}\n"
	# Shortest straw = smallest hash 
	Output += f"\nAnd {Users[0]} is the lucky (?) participant who pulls the shortest straw."
	await Discord_chan.send(Output)
	await IRC_manager.GCI().Safe_message(IRC_chan, Output)

@ergostraws.command(name="draw")
async def Discord_ergostraws_draw(Context):
	"""Pull a straw from the bag."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!ergostraws draw")
		await Ergostraws_draw(Bridge)

async def IRC_ergostraws_draw(Bridge):
	await Ergostraws_draw(Bridge)

async def Ergostraws_empty(Bridge):
	global Ergobag
	IRC_chan = Bridge["irc_chan"]
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	Ergobag["Common_key"] = {}
	Ergobag["Users"] = []
	Output = "The bag is now empty."
	await Context.send(Output)
	await IRC_manager.GCI().Safe_message(IRC_chan, Output)

@ergostraws.command(name="empty")
async def Discord_ergostraws_empty(Context):
	"""Empty the bag of straws (reset the poll)."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!ergostraws empty")
		await Ergostraws_empty(Bridge)

async def IRC_ergostraws_empty(Bridge):
	await Ergostraws_empty(Bridge)
