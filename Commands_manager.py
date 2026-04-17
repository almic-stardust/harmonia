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
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Output = "The !help command is only available on Discord."
	await Discord_chan.send(Output)
	await IRC_manager.GCI().Safe_message(IRC_chan, Output)

###############################################################################
# !roll
###############################################################################

async def Roll_dices(Bridge, Dices):
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
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
		Output = "Format has to be in NdN."
		await Discord_chan.send(Output)
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
		return
	await Discord_chan.send(Rolls)
	await IRC_manager.GCI().Safe_message(IRC_chan, Rolls)

@bot.command()
async def roll(Context, Dices: str):
	"""Roll dices in NdN format"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# If the Discord chan is bridged to an IRC chan, relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, f"!roll {Dices}")
		await Roll_dices(Bridge, Dices)

async def IRC_roll(Bridge, Dices):
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Dices = Dices.replace("!roll", "")
	if not Dices:
		Output = "Usage: !roll NdN"
		await Discord_chan.send(Output)
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
		return
	await Roll_dices(Bridge, Dices)

###############################################################################
# !straws
###############################################################################

def Straws_current_state():
	global Straws_bag
	Output = ""
	Presence_participants = False
	Presence_straws = False
	Display_help = False
	if len(Straws_bag["Users"]) > 0:
		Presence_participants = True
		Output += "The participants between whom to draw are: "
		Output += ", ".join(Straws_bag["Users"]) + ".\n\n"
	if len(Straws_bag["Common_key"]) > 0:
		Presence_straws = True
		Output += "The following users gave the following words:\n"
		for Author in Straws_bag["Common_key"].keys():
			Output += f"[{Author}] {Straws_bag['Common_key'][Author]}\n"
	if not Presence_participants:
		Display_help = True
		if Presence_straws:
			Output += "\nBut no participants between whom to draw. "
		else:
			Output += "No participants between whom to draw, and the bag is empty.\n"
	if Presence_participants and not Presence_straws:
		Display_help = True
		Output += "But the bag is empty. "
	return Output, Display_help

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
			IRC_chan = Bridge["irc_chan"]
			Author = Context.author.display_name
			# Relay on IRC the command sent on Discord
			await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!straws")
			Output, Display_help = Straws_current_state()
			if not Display_help:
				await Context.send(Output)
				await IRC_manager.GCI().Safe_message(IRC_chan, Output)
			else:
				Output += "See “!help straws"
				await Context.send(Output + "”.")
				await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")

async def IRC_straws(Bridge):
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Output, Display_help = Straws_current_state()
	if not Display_help:
		await Discord_chan.send(Output)
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
	else:
		Output += "See “!help straws"
		await Discord_chan.send(Output + "”.")
		await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")

@straws.command(name="help")
async def Discord_straws_help(Context):
	"""Place holder to redirect towards “!help straws”."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!straws help")
		Output = "See “!help straws"
		await Context.send(Output + "”.")
		await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")

async def IRC_straws_help(Bridge):
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Output = "See “!help straws"
	await Discord_chan.send(Output + "”.")
	await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")

async def Straws_add(Bridge, Author, Action, Straw, Context=None):
	global Straws_bag
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
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
		if Action == "Participate":
			if Author not in Straws_bag["Users"]:
				Straws_bag["Users"].append(Author)
			Straws_bag["Common_key"].update({Author: Straw})
		if Action == "Contribute":
			Straws_bag["Common_key"].update({Author: Straw})
	except Exception as Error:
		print(f"[Commands] Straws_add(): {Error}")
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

@straws.command(name="participate")
async def Discord_straws_participate(Context, *, Word: str):
	"""Put a straw in the bag (and participate in the draw)."""
	# A straw is a word, or several that will be concatenated, in both cases up to 30 letters
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author,
				f"!straws participate {Word}"
		)
		await Straws_add(Bridge, Author, "Participate", Word, Context)

async def IRC_straws_participate(Bridge, Author, Straw):
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Straw = Straw.replace("!straws participate", "")
	if not Straw:
		Output = "Usage: !straws participate Word"
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
		await Discord_chan.send(Output)
		return
	await Straws_add(Bridge, Author, "Participate", Straw)

@straws.command(name="contribute")
async def Discord_straws_contribute(Context, *, Word: str):
	"""Put a straw in the bag (without participating in the draw)."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author,
				f"!straws contribute {Word}"
		)
		await Straws_add(Bridge, Author, "Contribute", Word, Context)

async def IRC_straws_contribute(Bridge, Author, Straw):
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Straw = Straw.replace("!straws contribute", "")
	if not Straw:
		Output = "Usage: !straws contribute Word"
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
		await Discord_chan.send(Output)
		return
	await Straws_add(Bridge, Author, "Contribute", Straw)

async def Straws_users(Bridge, Users):
	global Straws_bag
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Straws_bag["Users"] = Users.split()
	Output = "The list of users has been set."
	await IRC_manager.GCI().Safe_message(IRC_chan, Output)
	await Discord_chan.send(Output)

@straws.command(name="users")
async def Discord_straws_users(Context, *, Users: str):
	"""Set the list of users participating in the draw."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, f"!straws users {Users}")
		await Straws_users(Bridge, Users)

async def IRC_straws_users(Bridge, Users):
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Users = Users.replace("!straws users", "")
	if not Users:
		Output = "No users provided! Usage: !straws users User1 User2 …"
		await Discord_chan.send(Output)
		await IRC_manager.GCI().Safe_message(IRC_chan, Output)
		return
	await Straws_users(Bridge, Users)

async def Straws_draw(Bridge):
	global Straws_bag
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	if len(Straws_bag["Common_key"]) == 0:
		Output = "No straws to draw from. See “!help straws"
		await Discord_chan.send(Output + "”.")
		await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")
		return
	if len(Straws_bag["Users"]) == 0:
		Output = "No participants between whom to draw. See “!help straws"
		await Discord_chan.send(Output + "”.")
		await IRC_manager.GCI().Safe_message(IRC_chan, Output + "” (on Discord).")
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
	await Discord_chan.send(Output)
	await IRC_manager.GCI().Safe_message(IRC_chan, Output)

@straws.command(name="draw")
async def Discord_straws_draw(Context):
	"""Pull a straw from the bag."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!straws draw")
		await Straws_draw(Bridge)

async def IRC_straws_draw(Bridge):
	await Straws_draw(Bridge)

async def Straws_reset(Bridge):
	global Straws_bag
	IRC_chan, Discord_chan = await Gears.Get_channels(Bridge)
	Straws_bag["Common_key"] = {}
	Straws_bag["Users"] = []
	Output = "The list of participants has been deleted, and the bag is now empty."
	await Discord_chan.send(Output)
	await IRC_manager.GCI().Safe_message(IRC_chan, Output)

@straws.command(name="reset")
async def Discord_straws_reset(Context):
	"""Reset the draw (delete participants and straws)."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		IRC_chan = Bridge["irc_chan"]
		Author = Context.author.display_name
		# Relay on IRC the command sent on Discord
		await IRC_manager.GCI().Relay_Discord_message(IRC_chan, Author, "!straws reset")
		await Straws_reset(Bridge)

async def IRC_straws_reset(Bridge):
	await Straws_reset(Bridge)
