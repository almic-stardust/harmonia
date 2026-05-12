# -*- coding: utf-8 -*-

import inspect
import random
import re
import hashlib
import datetime
from datetime import timedelta

from Config_manager import Config
import DB_manager
import Gears
import Discord_manager
from Discord_manager import bot
import IRC_manager

Straws_bag = {}
Straws_bag["Common_key"] = {}
Straws_bag["Users"] = []

###############################################################################
# Dispatch IRC commands
###############################################################################

async def IRC_commands_dispatcher(Bridge, User, Text):

	Straws_infos = {
			"Name":			"straws",
			"Dispatcher":	Straws_dispatcher,
			#		 		 Fonction					User variable?	Arguments?
			"Direct_call":	(IRC_straws,				False),
	"Subcommands": {
			"help":			(IRC_straws_help,							False),
			"participate":	(IRC_straws_participate,					True),
			"contribute":	(IRC_straws_contribute,						True),
			"users":		(IRC_straws_users,							True),
			"draw":			(IRC_straws_draw,							False),
			"reset":		(IRC_straws_reset,							False),
	}}
	Polls_infos = {
			"Name":			"polls",
			"Dispatcher":	Polls_dispatcher,
			#		 		 Fonction					User variable?	Arguments?
			"Direct_call":	(IRC_polls,					True),
	"Subcommands": {
			"help":			(IRC_polls_help,							False),
			"members":		(IRC_polls_members,							True),
	}}

	Commands = { #		 Destination (funct or dict)	User variable?	Arguments?
			"!help":	(No_help_for_IRC,				False,			False),
			"!roll":	(IRC_roll,						False,			True),
			"!straws":	(Straws_infos,					True,			True),
			"!polls":	(Polls_infos,					True,			True),
	}

	Parts = Text.split(maxsplit=1)
	Command = Parts[0]
	Remainder = Parts[1] if len(Parts) > 1 else None
	if Command not in Commands:
		Output = "Invalid command. See “!help”."
		Output_IRC = "Invalid command. See “!help” (on Discord)."
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Command_infos, With_user, With_args = Commands[Command]
	# Commands without subcommands
	if inspect.isfunction(Command_infos):
		# It’s clearer to call Function(…) with a variable named Function
		Function = Command_infos
		if With_user and With_args:
			await Function(Bridge, User, Remainder)
		elif With_args:
			await Function(Bridge, Remainder)
		elif With_user:
			await Function(Bridge, User)
		else:
			await Function(Bridge)
	else:
		if With_user:
			await IRC_subcommands_dispatcher(Bridge, Command_infos, User, Remainder)
		else:
			await IRC_subcommands_dispatcher(Bridge, Command_infos, None, Remainder)

async def IRC_subcommands_dispatcher(Bridge, Command_infos, User, Remainder):
	if not Remainder:
		Function, With_user = Command_infos["Direct_call"]
		if With_user:
			await Function(Bridge, User)
		else:
			await Function(Bridge)
		return
	Dispatcher_function = Command_infos["Dispatcher"]
	Subcommands = Command_infos["Subcommands"]
	Parts = Remainder.split(maxsplit=1)
	Subcommand = Parts[0]
	Arguments = Parts[1] if len(Parts) > 1 else None
	if Subcommand not in Subcommands:
		Output = f"Invalid subcommand. See “!help {Command_infos['Name']}”."
		Output_IRC = f"Invalid subcommand. See “!help {Command_infos['Name']}” (on Discord)."
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Function, With_args = Subcommands[Subcommand]
	# Subcommands that don’t require arguments
	if not With_args:
		await Function(Bridge)
		return
	await Dispatcher_function(Bridge, Subcommand, Function, User, Arguments)

async def Straws_dispatcher(Bridge, Subcommand, Function, User, Arguments):
	if not Arguments:
		if Subcommand in {"participate", "contribute"}:
			Help_usage = f"Usage: !straws {Subcommand} Word"
		elif Subcommand == "users":
			Help_usage = "Usage: !straws users User1 User2 …"
		await Gears.Send(Bridge, Help_usage)
		return
	if Subcommand in {"participate", "contribute"}:
		await Function(Bridge, User, Arguments)
	else:
		await Function(Bridge, Arguments)

async def Polls_dispatcher(Bridge, Subcommand, Function, User, Arguments):
	#if not Arguments:
	#	if Subcommand == "":
	#		Help_usage = f"Usage: !polls {Subcommand} "
	#	await Gears.Send(Bridge, Help_usage)
	#	return
	#if Subcommand in {"vote"}:
	#	await Function(Bridge, User, Arguments)
	#else:
	#	await Function(Bridge, Arguments)
	await Function(Bridge, Arguments)

###############################################################################
# Misc
###############################################################################

async def No_help_for_IRC(Bridge):
	await Gears.Send(Bridge, "The !help command is only available on Discord.")

###############################################################################
# !roll
###############################################################################

# In this module, the Author variable will be used to indicate whether the message was sent from
# Discord, and if so, by which user.
async def Roll_Dice(Bridge, Dice, Author=None):
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC. Otherwise, IRC users will see a response
	# from the bot, without seeing the command that prompted it.
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !roll {Dice}\n"
	try:
		# Accept NDN as well as NdN
		Dice = Dice.lower()
		Number_rolls, Limit = map(int, Dice.split("d"))
		if Number_rolls > 500:
			await Gears.Send(Bridge, "You really need to throw more than 500 dice at once?")
			return
		if Limit > 1000:
			await Gears.Send(Bridge, "The dice are limited to 1000 faces.")
			return
		Rolls = []
		for _ in range(Number_rolls):
			Roll = random.randint(1, Limit)
			Rolls.append(str(Roll))
		Rolls = ", ".join(Rolls)
	except Exception as Error:
		print(f"[Commands] Roll_Dice(): {Error}")
		Output = "Format has to be NdN."
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Output = Rolls
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@bot.command()
async def roll(Context, Dice: str):
	"""Roll Dice in NdN format"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Roll_Dice(Bridge, Dice, Context.author.display_name)

async def IRC_roll(Bridge, Dice):
	if not Dice:
		await Gears.Send(Bridge, "Usage: !roll NdN")
		return
	await Roll_Dice(Bridge, Dice)

###############################################################################
# !straws
###############################################################################

async def Straws_current_state(Bridge, Author=None):

	global Straws_bag
	Presence_participants = False
	Presence_straws = False
	Display_help = False
	Output = ""
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
	Output = Output
	Output_IRC += Output
	if Display_help:
		Output += "See “!help straws”."
		Output_IRC += "See “!help straws” (on Discord)."
	await Gears.Send(Bridge, Output, Output_IRC)

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
	Output = "See “!help straws”."
	Output_IRC += "See “!help straws” (on Discord)."
	await Gears.Send(Bridge, Output, Output_IRC)

@straws.command(name="help")
async def Discord_straws_help(Context):
	"""Placeholder to redirect towards “!help straws”."""
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
	IRC_instance = IRC_manager.GCI()
	# The command comes from Discord: relay the command on IRC + confirmation via DM
	if Context:
		if IRC_instance:
			await IRC_instance.Relay_Discord_message(
					Bridge["irc_chan"], IRC_chan, User, f"!straws {Action} {Straw}"
			)
		await Context.author.send(Output)
	# The command comes from IRC: confirmation via query
	else:
		if IRC_instance:
			await IRC_instance.Safe_message(User, Output)

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
	if len(Users) > 50:
		Output = "The draw is limited to 50 users."
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Straws_bag["Users"] = []
	for User in Users.split():
		Straws_bag["Users"].append(User[:30])
	Output = "The list of users has been set (usernames are limited to 30 characters)."
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

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

	if len(Straws_bag["Users"]) == 0:
		Output = "No participants between whom to draw. See “!help straws”."
		Output_IRC += "No participants between whom to draw. See “!help straws” (on Discord)."
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	if len(Straws_bag["Common_key"]) == 0:
		Output = "No straws to draw from. See “!help straws”."
		Output_IRC += "No straws to draw from. See “!help straws” (on Discord)."
		await Gears.Send(Bridge, Output, Output_IRC)
		return

	Common_key = " ".join(Straws_bag["Common_key"].values())
	Hashes = {}
	for User in Straws_bag["Users"]:
		# Create a dedicated key for each user, by appending their name to the common key
		User_key = (Common_key + User).encode("utf8")
		# Calculate a hash for each user’s key
		Hashes[User] = hashlib.sha512(User_key).hexdigest()
	# To avoid modifying the original list, create an sorted copy, from smallest to biggest hash
	Users = sorted(Straws_bag["Users"], key=lambda User: Hashes[User])

	Output = "The participants between whom to draw are: "
	Output += ", ".join(Straws_bag["Users"]) + ".\n\n"
	Output += f"The common key is: “{Common_key}”.\n"
	Output += "Hash for each participant:\n"
	for User in Straws_bag["Users"]:
		# Display only the beginning of the hash: it’s more readable, and sufficient to verify
		Beginning_hash = Hashes[User][:30]
		Output += f"[{User}] {Beginning_hash}[…]\n"
	# Shortest straw = smallest hash 
	Output += f"\nAnd {Users[0]} is the lucky (?) participant who pulls the shortest straw."
	Output = Output
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

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
	Output = "The list of participants has been deleted, and the bag is now empty."
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@straws.command(name="reset")
async def Discord_straws_reset(Context):
	"""Reset the draw (delete participants and straws)."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_reset(Bridge, Context.author.display_name)

async def IRC_straws_reset(Bridge):
	await Straws_reset(Bridge)

###############################################################################
# !polls
###############################################################################

@bot.group()
async def polls(Context):
	"""Organize votes and participate in them."""
	if Context.invoked_subcommand is None:
		# If there’s something after “!polls”, but it’s not a valid subcommand
		if Context.subcommand_passed is not None:
			await Context.send("Invalid subcommand. See “!help polls”.")
			return
		# If no subcommand is invoked: “!polls” = “!polls list”
		Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
		if Bridge:
			await Gears.Send(Bridge, "Display the last 5 votes, prioritizing ongoing extended.")

async def IRC_polls(Bridge, User):
	await Gears.Send(Bridge, "Display the last 5 votes, prioritizing ongoing extended.")

async def Polls_help(Bridge, Author=None):
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !polls help\n"
	Output = "See “!help polls”."
	Output_IRC += "See “!help polls” (on Discord)."
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="help")
async def Discord_polls_help(Context):
	"""Placeholder to redirect towards “!help polls”."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_help(Bridge, Context.author.display_name)

async def IRC_polls_help(Bridge):
	await Polls_help(Bridge)

def Polls_voting_rights(User_infos):
	if not User_infos["Renewals"]:
		return User_infos
	Renewals_years = []
	Renewals_dates = []
	for Year in User_infos["Renewals"]:
		Renewals_years.append(Year)
		Renewals_dates.extend(User_infos["Renewals"][Year])
	Renewals_years.sort()
	Renewals_dates.sort()
	User_infos["Registration"] = Renewals_dates[0]
	User_infos["Last_renewal"] = Renewals_dates[-1]
	User_infos["Penultimate_year"] = None
	if len(Renewals_years) >= 2:
		Penultimate_year = Renewals_years[-2]
		User_infos["Penultimate_year"] = datetime.datetime.strptime(str(Penultimate_year), "%Y")
	Now = datetime.datetime.now()
	# Registration over a year ago
	if User_infos["Registration"] + timedelta(days=365) <= Now \
			and User_infos["Last_renewal"] + timedelta(days=365) >= Now:
		User_infos["Can_vote"] = True
	# Former member who renewed their membership less than 3 months ago
	elif User_infos["Penultimate_year"] \
			and User_infos["Penultimate_year"] + timedelta(days=365) <= Now \
			and User_infos["Last_renewal"] + timedelta(days=90) >= Now:
		User_infos["Can_vote"] = True
	return User_infos

async def Polls_members(Bridge, List_of_users, Author=None):
	Users_table = Config["users"]["db_table"]
	Users = DB_manager.Users_fetch_users(Users_table)
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		if List_of_users:
			Output_IRC = f"<\x02{Author}\x02> !polls members {List_of_users}\n"
		else:
			Output_IRC = f"<\x02{Author}\x02> !polls members\n"
	if not List_of_users:
		Output = "Display a list of members with voting rights."
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	# List_of_users is a string
	for User in List_of_users.split():
		User_infos = {}
		User_infos["Pseudo"] = User
		User_ID = DB_manager.Users_check_presence(Users_table, User_infos)
		if User_ID:
			User_infos = Users[User_ID]
		User_infos["Can_vote"] = False
		if User_ID:
			User_infos = Polls_voting_rights(User_infos)
			if User_infos["Can_vote"]:
				Output += f"{User} can vote "
			else:
				Output += f"{User} can’t vote "
			Last_renewal = datetime.datetime.strftime(User_infos["Last_renewal"], "%d/%m/%Y")
			Registration = datetime.datetime.strftime(User_infos["Registration"], "%d/%m/%Y")
			if User_infos["Penultimate_year"]:
				Penultimate_year = datetime.datetime.strftime(User_infos["Penultimate_year"], "%Y")
				Output += f"(Last renewal {Last_renewal} | Penultimate for {Penultimate_year})\n"
			else:
				Output += f"(Last renewal {Last_renewal} | Registration {Registration})\n"
		else:
			Output += f"{User} isn’t a member.\n"
	Output = Output
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="members")
async def Discord_polls_members(Context, *, List_of_users=None):
	"""Display informations about members’ voting rights."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_members(Bridge, List_of_users, Context.author.display_name)

async def IRC_polls_members(Bridge, List_of_users):
	await Polls_members(Bridge, List_of_users)
