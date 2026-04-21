# -*- coding: utf-8 -*-

import random
import re
import hashlib

import Gears
from Discord_manager import bot
import Discord_manager
import IRC_manager

Straws_bag = {}
Straws_bag["Common_key"] = {}
Straws_bag["Users"] = []

###############################################################################
# General
###############################################################################

async def No_help_for_IRC(Bridge):
	await Gears.Send(Bridge, "The !help command is only available on Discord.")

###############################################################################
# !roll
###############################################################################

# In this module, the Author variable will be used to indicate whether the message was sent from
# Discord, and if so, by which user.
async def Roll_dices(Bridge, Dices, Author=None):
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC. Otherwise, IRC users will see a response
	# from the bot, without seeing the command that prompted it.
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !roll {Dices}\n"
	try:
		# Accept NDN as well as NdN
		Dices = Dices.lower()
		Number_rolls, Limit = map(int, Dices.split("d"))
		Rolls = []
		for _ in range(Number_rolls):
			Roll = random.randint(1, Limit)
			Rolls.append(str(Roll))
		Rolls = ", ".join(Rolls)
	except Exception as Error:
		print(f"[Commands] Roll_dices(): {Error}")
		Output_Discord = "Format has to be NdN."
		Output_IRC += Output_Discord
		await Gears.Send(Bridge, Output_Discord, Output_IRC)
		return
	Output_Discord = Rolls
	Output_IRC += Output_Discord
	await Gears.Send(Bridge, Output_Discord, Output_IRC)

@bot.command()
async def roll(Context, Dices: str):
	"""Roll dices in NdN format"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Roll_dices(Bridge, Dices, Context.author.display_name)

async def IRC_roll(Bridge, Dices):
	await Roll_dices(Bridge, Dices)

###############################################################################
# !straws
###############################################################################

async def Straws_current_state(Bridge, Author=None):

	global Straws_bag
	Output = ""
	Presence_participants = False
	Presence_straws = False
	Display_help = False
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !straws\n"

	if len(Straws_bag["Users"]) > 0:
		Presence_participants = True
		Output += "The participants between whom to draw are: "
		Output += ", ".join(Straws_bag["Users"]) + ".\n\n"
	if len(Straws_bag["Common_key"]) > 0:
		Presence_straws = True
		Output += "The following users gave the following words:\n"
		for User in Straws_bag["Common_key"].keys():
			Output += f"[{User}] {Straws_bag['Common_key'][User]}\n"

	if not Presence_participants:
		Display_help = True
		if Presence_straws:
			Output += "\nBut no participants between whom to draw. "
		else:
			Output += "No participants between whom to draw, and the bag is empty.\n"
	if Presence_participants and not Presence_straws:
		Display_help = True
		Output += "But the bag is empty. "
	Output_Discord = Output
	Output_IRC += Output
	if Display_help:
		Output_Discord += "See “!help straws”."
		Output_IRC += "See “!help straws” (on Discord)."
	await Gears.Send(Bridge, Output_Discord, Output_IRC)

@bot.group()
async def straws(Context):
	"""Draw straws among a group, with a reproducible pseudo-randomness."""
	if Context.invoked_subcommand is None:
		# If there’s something after “!straws”, but it’s not a valid subcommand
		if Context.subcommand_passed is not None:
			await Context.send("Invalid subcommand. See “!help straws”.")
			return
		# If no subcommand is invoked, show what’s currently in the bag
		Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
		if Bridge:
			await Straws_current_state(Bridge, Context.author.display_name)

async def IRC_straws(Bridge):
	await Straws_current_state(Bridge)

async def Straws_help(Bridge, Author=None):
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !straws help\n"
	Output_Discord = "See “!help straws”."
	Output_IRC += "See “!help straws” (on Discord)."
	await Gears.Send(Bridge, Output_Discord, Output_IRC)

@straws.command(name="help")
async def Discord_straws_help(Context):
	"""Place holder to redirect towards “!help straws”."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_help(Bridge, Context.author.display_name)

async def IRC_straws_help(Bridge):
	await Straws_help(Bridge)

async def Straws_add(Bridge, User, Action, Straw, Context=None):
	global Straws_bag
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
		if Action == "participate":
			if User not in Straws_bag["Users"]:
				Straws_bag["Users"].append(User)
			Straws_bag["Common_key"].update({User: Straw})
		if Action == "contribute":
			Straws_bag["Common_key"].update({User: Straw})
	except Exception as Error:
		print(f"[Commands] Straws_add(): {Error}")
		await Gears.Send(Bridge, "Your straw couldn’t be added in the bag!")
		return
	Output = f"Your straw “{Straw}” has been added in the bag."
	# The command comes from Discord: relay the command on IRC + confirmation via DM
	if Context:
		IRC_chan = Bridge["irc_chan"]
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, User, f"!straws {Action} {Straw}")
		await Context.author.send(Output)
	# The command comes from IRC: confirmation via query
	else:
		await IRC_manager.GCI().Safe_message(User, Output)

@straws.command(name="participate")
async def Discord_straws_participate(Context, *, Word: str):
	"""Put a straw in the bag (and participate in the draw)."""
	# A straw is a word, or several that will be concatenated, in both cases up to 30 letters
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_add(Bridge, Context.author.display_name, "participate", Word, Context)

async def IRC_straws_participate(Bridge, User, Word):
	await Straws_add(Bridge, User, "participate", Word)

@straws.command(name="contribute")
async def Discord_straws_contribute(Context, *, Word: str):
	"""Put a straw in the bag (without participating in the draw)."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_add(Bridge, Context.author.display_name, "contribute", Word, Context)

async def IRC_straws_contribute(Bridge, User, Word):
	await Straws_add(Bridge, User, "contribute", Word)

async def Straws_users(Bridge, Users, Author=None):
	global Straws_bag
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !straws users {Users}\n"
	Straws_bag["Users"] = Users.split()
	Output_Discord = "The list of users has been set."
	Output_IRC += Output_Discord
	await Gears.Send(Bridge, Output_Discord, Output_IRC)

@straws.command(name="users")
async def Discord_straws_users(Context, *, Users: str):
	"""Set the list of users participating in the draw."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_users(Bridge, Users, Context.author.display_name)

async def IRC_straws_users(Bridge, Users):
	await Straws_users(Bridge, Users)

async def Straws_draw(Bridge, Author=None):

	global Straws_bag
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !straws draw\n"

	if len(Straws_bag["Common_key"]) == 0:
		Output_Discord = "No straws to draw from. See “!help straws”."
		Output_IRC += "No straws to draw from. See “!help straws” (on Discord)."
		await Gears.Send(Bridge, Output_Discord, Output_IRC)
		return
	if len(Straws_bag["Users"]) == 0:
		Output_Discord = "No participants between whom to draw. See “!help straws”."
		Output_IRC += "No participants between whom to draw. See “!help straws” (on Discord)."
		await Gears.Send(Bridge, Output_Discord, Output_IRC)
		return

	Common_key = " ".join(Straws_bag["Common_key"].values())
	Hashes = {}
	for User in Straws_bag["Users"]:
		# Create a dedicated key for each user, by appending their name to the common key, and then
		# calculate a hash for each user’s key
		Hash = hashlib.sha256((Common_key + User).encode("utf8")).hexdigest()
		Hashes[User] = Hash
	# To avoid modifying the original list, create an sorted copy, from smallest to biggest hash
	Users = sorted(Straws_bag["Users"], key=lambda User: Hashes[User])

	Output = "The participants between whom to draw are: "
	Output += ", ".join(Straws_bag["Users"]) + ".\n\n"
	Output += f"The common key is: “{Common_key}”.\n"
	Output += "Hash for each participant:\n"
	for User in Straws_bag["Users"]:
		Output += f"[{User}] {Hashes[User]}\n"
	# Shortest straw = smallest hash 
	Output += f"\nAnd {Users[0]} is the lucky (?) participant who pulls the shortest straw."
	Output_Discord = Output
	Output_IRC += Output
	await Gears.Send(Bridge, Output_Discord, Output_IRC)

@straws.command(name="draw")
async def Discord_straws_draw(Context):
	"""Pull a straw from the bag."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_draw(Bridge, Context.author.display_name)

async def IRC_straws_draw(Bridge):
	await Straws_draw(Bridge)

async def Straws_reset(Bridge, Author=None):
	global Straws_bag
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !straws reset\n"
	Straws_bag["Common_key"] = {}
	Straws_bag["Users"] = []
	Output_Discord = "The list of participants has been deleted, and the bag is now empty."
	Output_IRC += Output_Discord
	await Gears.Send(Bridge, Output_Discord, Output_IRC)

@straws.command(name="reset")
async def Discord_straws_reset(Context):
	"""Reset the draw (delete participants and straws)."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_reset(Bridge, Context.author.display_name)

async def IRC_straws_reset(Bridge):
	await Straws_reset(Bridge)
