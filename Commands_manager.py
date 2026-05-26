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

async def IRC_dispatcher(Bridge, User, Text):

	# The IRC_* functions are used when arguments are mandatory, in order to handle them
	Infos_straws = {
	#				 		 Fonction					Arguments?		User variable?
	"Direct_call":			(Straws_current_state,						False),
	"Subcommands": {
			"help":			(Straws_help,				False,			False),
			"participate":	(IRC_straws_participate,	True,			True),
			"contribute":	(IRC_straws_contribute,		True,			True),
			"users":		(IRC_straws_users,			True,			False),
			"draw":			(Straws_draw,				False,			False),
			"reset":		(Straws_reset,				False,			False),
	}}
	Infos_polls = {
	#				 		 Fonction					Arguments?		User variable?
	"Direct_call":			(IRC_polls,									False),
	"Subcommands": {
			"help":			(Polls_help,				False,			False),
			"members":		(Polls_members,				True,			False),
			"create":		(Polls_create,				True,			True),
			"close":		(IRC_polls_close,			True,			True),
			"vote":			(Polls_vote,				True,			True),
			"info":			(Polls_info,				True,			False),
	}}

	Commands = { #		 Destination (funct or dict)	Arguments?		User variable?
			"help":		(No_help_for_IRC,				False,			False),
			"roll":		(IRC_roll,						True,			False),
			"straws":	(Infos_straws,					True,			True),
			"polls":	(Infos_polls,					True,			True),
	}

	Parts = Text.split(maxsplit=1)
	Command = Parts[0].replace("!", "")
	Remainder = Parts[1] if len(Parts) > 1 else None
	if Command not in Commands:
		Output = "Invalid command. See “!help”"
		Output_IRC = Output + " (on Discord)."
		Output += "."
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Infos_command, With_args, With_user = Commands[Command]
	# Commands without subcommands
	if inspect.isfunction(Infos_command):
		Function = Infos_command
		Arguments = Remainder
	else:
		if not Remainder:
			Function, With_user = Infos_command["Direct_call"]
			if With_user:
				await Function(Bridge, User)
			else:
				await Function(Bridge)
			return
		Infos_subcommands = Infos_command["Subcommands"]
		Parts = Remainder.split(maxsplit=1)
		Subcommand_called = Parts[0]
		Arguments = Parts[1] if len(Parts) > 1 else None
		if Subcommand_called not in Infos_subcommands:
			Output = f"Invalid subcommand. See “!help {Command}”"
			Output_IRC = Output + " (on Discord)."
			Output += "."
			await Gears.Send(Bridge, Output, Output_IRC)
			return
		Function, With_args, With_user = Infos_subcommands[Subcommand_called]

	if With_args and With_user:
		await Function(Bridge, User, Arguments)
	elif With_args:
		await Function(Bridge, Arguments)
	elif With_user:
		await Function(Bridge, User)
	else:
		await Function(Bridge)

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
async def roll(Context, Dice):
	"""Roll Dice in NdN format.
	Parameters
	----------
	Dice : str
		“!roll NdN”"""
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
	Output_IRC += Output
	if Display_help:
		Help_usage = "See “!help straws”"
		Output += Help_usage + "."
		Output_IRC += Help_usage + " (on Discord)."
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

async def Straws_help(Bridge, Author=None):
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !straws help\n"
	Output = "See “!help straws”"
	Output_IRC += Output + " (on Discord)."
	Output += "."
	await Gears.Send(Bridge, Output, Output_IRC)

@straws.command(name="help")
async def Discord_straws_help(Context):
	"""Placeholder redirecting towards “!help straws”."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_help(Bridge, Context.author.display_name)

async def Straws_add(Bridge, User, Action, Straw, Context=None):
	global Straws_bag
	IRC_instance = IRC_manager.GCI()
	# If the command was sent on Discord, relay it on IRC
	# No usage of Output_IRC for this function, because confirmations are sent privately
	if Context:
		if IRC_instance:
			await IRC_instance.Relay_Discord_message(
					Bridge["irc_chan"], User, f"!straws {Action} {Straw}"
			)
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
	# The command comes from Discord, confirmation via DM
	if Context:
		await Context.author.send(Output)
	# The command comes from IRC, confirmation via query
	else:
		if IRC_instance:
			await IRC_instance.Safe_message(User, Output)

@straws.command(name="participate")
async def Discord_straws_participate(Context, *, Word):
	"""Put a straw in the bag (and participate in the draw).
	Parameters
	----------
	Word : str
		“!straws participate Word”"""
	# A straw is a word, or several that will be concatenated, in both cases up to 30 letters
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_add(Bridge, Context.author.display_name, "participate", Word, Context)

async def IRC_straws_participate(Bridge, User, Word):
	if not Word:
		await Gears.Send(Bridge, "Usage: !straws participate Word")
		return
	await Straws_add(Bridge, User, "participate", Word)

@straws.command(name="contribute")
async def Discord_straws_contribute(Context, *, Word):
	"""Put a straw in the bag (without participating in the draw).
	Parameters
	----------
	Word : str
		“!straws contribute Word”"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_add(Bridge, Context.author.display_name, "contribute", Word, Context)

async def IRC_straws_contribute(Bridge, User, Word):
	if not Word:
		await Gears.Send(Bridge, "Usage: !straws contribute Word")
		return
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
async def Discord_straws_users(Context, *, Users):
	"""Set the list of users participating in the draw.
	Parameters
	----------
	Users : str
		“!straws users User1 User2 …”"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_users(Bridge, Users, Context.author.display_name)

async def IRC_straws_users(Bridge, Users):
	if not Users:
		await Gears.Send(Bridge, "Usage: !straws users User1 User2 …")
		return
	await Straws_users(Bridge, Users)

async def Straws_draw(Bridge, Author=None):

	global Straws_bag
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !straws draw\n"

	if len(Straws_bag["Users"]) == 0:
		Output = "No participants between whom to draw. See “!help straws”"
		Output_IRC += Output + " (on Discord)."
		Output += "."
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	if len(Straws_bag["Common_key"]) == 0:
		Output = "No straws to draw from. See “!help straws”"
		Output_IRC += Output + " (on Discord)."
		Output += "."
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
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@straws.command(name="draw")
async def Discord_straws_draw(Context):
	"""Pull a straw from the bag."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Straws_draw(Bridge, Context.author.display_name)

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
			await Gears.Send(Bridge, "Last 5 polls (prioritizing active ones) :")

async def IRC_polls(Bridge):
	await Gears.Send(Bridge, "Last 5 polls (prioritizing active ones) :")

async def Polls_help(Bridge, Author=None):
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !polls help\n"
	Output = "See “!help polls”"
	Output_IRC += Output + " (on Discord)."
	Output += "."
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="help")
async def Discord_polls_help(Context):
	"""Placeholder redirecting towards “!help polls”."""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_help(Bridge, Context.author.display_name)

def Polls_voting_rights(User_infos):
	User_infos["Can_vote"] = False
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
	Unregistered = []
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		if List_of_users:
			Output_IRC = f"<\x02{Author}\x02> !polls members {List_of_users}\n"
		else:
			Output_IRC = f"<\x02{Author}\x02> !polls members\n"
	# “!polls members” lists all members with voting rights
	if not List_of_users:
		List_of_users_from_argument = False
		Users_to_display = Users
	else:
		List_of_users_from_argument = True
		Users_to_display = {}
		# List_of_users is a string
		for User in List_of_users.split():
			User_infos = {}
			User_infos["Pseudo"] = User
			User_ID = DB_manager.Users_check_presence(Users_table, User_infos)
			if User_ID:
				Users_to_display[User_ID] = Users[User_ID]
			else:
				Unregistered.append(User)
	if len(Unregistered) > 0:
		if len(Unregistered) == 1:
			Output += f"{Unregistered[0]} isn’t a member.\n"
		else:
			for User in Unregistered:
				Output += f"{User} "
			Output += "aren’t members.\n"
		if not Users_to_display:
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
	for User_ID in Users_to_display:
		User_infos = Users_to_display[User_ID]
		User_infos = Polls_voting_rights(User_infos)
		if User_infos["Can_vote"]:
			Output += f"{User_infos['Pseudo']} "
		# If we display all voting members, keep a concise display
		if not List_of_users_from_argument:
			continue
		if User_infos["Can_vote"]:
			Output += f"can vote "
		else:
			Output += f"{User_infos['Pseudo']} can’t vote "
		Registration = datetime.datetime.strftime(User_infos["Registration"], "%d/%m/%Y")
		Last_renewal = datetime.datetime.strftime(User_infos["Last_renewal"], "%d/%m/%Y")
		if User_infos["Penultimate_year"]:
			Penultimate_year = datetime.datetime.strftime(User_infos["Penultimate_year"], "%Y")
			Output += f"(Last renewal {Last_renewal} | Penultimate for {Penultimate_year})\n"
		else:
			Output += f"(last renewal {Last_renewal} | registration {Registration})\n"
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="members")
async def Discord_polls_members(Context, *, Members=None):
	"""Display informations about members’ voting rights.
	Parameters
	----------
	Members : str
		(optional) “!straws members [Member1 Member2 …]”"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		# In the !help for this subcommand, it’s better to display Members instead of List_of_users
		await Polls_members(Bridge, Members, Context.author.display_name)

async def Polls_create(Bridge, User, Arguments, From_Discord=False):
	Polls_table = Config["polls"]["db_table"]
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if From_Discord:
		Output_IRC = f"<\x02{User}\x02> !polls create {Arguments}\n"
	if not Arguments:
		Output += "Usage: !polls create Subject | Choice 1 ; Choice 2 ; …"
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	if "|" in Arguments:
		Question, Choices = Arguments.split("|", 1)
		Question = Question.strip()
	else:
		Question = Arguments
		Choices = None
	if Choices and ";" in Choices:
		List_of_choices = []
		Choices = Choices.split(";")
		for Choice in Choices:
			Choice = Choice.strip()
			if Choice:
				List_of_choices.append(Choice)
		Choices = List_of_choices
		if len(Choices) == 1:
			Output += "If there’s only one choice, what’s the point of having a vote?"
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
	else:
		Choices = ["Yes", "No", "Abs"]
	Poll_ID = DB_manager.Polls_create(Polls_table, User, Question, Choices)
	Output += f"Poll #{Poll_ID}: {Question}\n["
	for Index, Choice in enumerate(Choices):
		Output += f"{Index + 1} = {Choice}"
		if Index + 1 < len(Choices):
			Output += "]   ["
		else:
			Output += "]\n"
	Output += f"Vote with: “!polls vote <Choice_number> [{Poll_ID}]”"
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="create")
async def Discord_polls_create(Context, *, Arguments):
	"""Create a new poll.
	Parameters
	----------
	Arguments : str
		syntax: “!polls create Subject | Choice 1 ; Choice 2 ; …”"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_create(Bridge, Context.author.display_name, Arguments, True)

async def Polls_close(Bridge, User, Is_moderator, Arguments, From_Discord=False):

	Polls_table = Config["polls"]["db_table"]
	Polls_IDs = []
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if From_Discord:
		if Arguments:
			Output_IRC = f"<\x02{User}\x02> !polls close {Arguments}\n"
		else:
			Output_IRC = f"<\x02{User}\x02> !polls close\n"

	# If no poll ID was given, automatically select the lastest
	if not Arguments:
		Poll_infos = DB_manager.Polls_fetch_last(Polls_table)
		if not Poll_infos:
			Output += "Error: no polls in the DB."
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
		Polls_IDs.append(Poll_infos["ID"])
	else:
		# To avoid a DB query later, if the lastest poll has been automatically selected
		Poll_infos = None
		for Poll_ID in Arguments.split():
			try:
				Polls_IDs.append(int(Poll_ID))
			except (TypeError, ValueError):
				Output += f"Error: {Poll_ID} is an invalid poll ID.\n"
				continue

	for Poll_ID in Polls_IDs:
		# Avoid a DB query, in case the lastest poll was automatically selected
		if len(Polls_IDs) > 1 or (len(Polls_IDs) == 1 and not Poll_infos):
			Poll_infos = DB_manager.Polls_fetch(Polls_table, Poll_ID)
		if not Poll_infos:
			Output += f"Error: poll #{Poll_ID}: doesn’t exist.\n"
			continue
		if not Poll_infos["Active"]:
			Output += f"Error: poll #{Poll_ID}: already closed.\n"
			continue
		# Moderators can also close polls
		if not (User == Poll_infos["Author"] or Is_moderator):
			Output += f"Error: poll #{Poll_ID}: only the author or a moderator can close a poll.\n"
			continue
		DB_manager.Polls_close(Polls_table, Poll_ID)
		Output += f"{User} closed poll #{Poll_ID} ({Poll_infos['Question']})\n"
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="close")
async def Discord_polls_close(Context, *, Arguments=None):
	"""Close one or several poll (the latest if no ID is specified).
	Parameters
	----------
	Arguments : int
		syntax: “!polls close [Poll_ID] [Poll_ID] [Poll_ID] …”"""
	Is_moderator = Context.author.guild_permissions.manage_messages
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_close(Bridge, Context.author.display_name, Is_moderator, Arguments, True)

async def IRC_polls_close(Bridge, User, Arguments=None):
	Is_user_op = IRC_manager.Is_op(Bridge["irc_chan"], User)
	await Polls_close(Bridge, User, Is_user_op, Arguments)

async def Polls_vote(Bridge, User, Arguments, Context=None):

	Users_table = Config["users"]["db_table"]
	Polls_table = Config["polls"]["db_table"]
	IRC_instance = IRC_manager.GCI()
	# If the command was sent on Discord, relay it on IRC
	# No usage of Output_IRC for this function, because user related errors are sent privately
	if Context:
		await IRC_instance.Relay_Discord_message(Bridge["irc_chan"], User,
				f"<\x02{User}\x02> !polls vote {Arguments}"
		)
	Help_usage = "Usage: !polls vote <Choice_number> [Poll_ID]"
	if not Arguments:
		await Gears.Send(Bridge, Help_usage)
		return

	Parts = Arguments.split()
	if len(Parts) == 2:
		try:
			Choice = int(Parts[0])
			Poll_ID = int(Parts[1])
			# To avoid a DB query later, if the lastest poll has been automatically selected
			Poll_infos = None
		except ValueError:
			await Gears.Send(Bridge, f"Error: invalid poll ID or choice number.\n" + Help_usage)
			return
	# If no poll ID was given, automatically select the lastest
	elif len(Parts) == 1:
		try:
			Choice = int(Parts[0])
		except ValueError:
			await Gears.Send(Bridge, f"Error: invalid choice number.\n" + Help_usage)
			return
		Poll_infos = DB_manager.Polls_fetch_last(Polls_table)
		if not Poll_infos:
			await Gears.Send(Bridge, "Error: no polls in the DB.")
			return
		Poll_ID = Poll_infos["ID"]
	else:
		await Gears.Send(Bridge, Help_usage)
		return

	User_infos = {"Pseudo": User}
	User_ID = DB_manager.Users_check_presence(Users_table, User_infos)
	if not User_ID:
		await Gears.Send_DM(User, Context, "Error: you’re not registered.")
		return
	Users = DB_manager.Users_fetch_users(Users_table)
	User_infos = Users[User_ID]
	User_infos = Polls_voting_rights(User_infos)
	if not User_infos["Can_vote"]:
		await Gears.Send_DM(User, Context, "Error: you don’t have voting rights.")
		return

	# Avoid a DB query, in case the lastest poll was automatically selected
	if not Poll_infos:
		Poll_infos = DB_manager.Polls_fetch(Polls_table, Poll_ID)
	if not Poll_infos:
		await Gears.Send(Bridge, "Error: poll not found. See “!polls list”")
		return
	if not Poll_infos["Active"]:
		await Gears.Send(Bridge, f"Error: poll #{Poll_ID} is closed. See “!polls list active”")
		return
	Number_of_choices = len(Poll_infos["Choices"])
	if Choice < 1 or Choice > Number_of_choices:
		await Gears.Send(Bridge, f"Error: invalid choice number. See “!polls info {Poll_ID}”")
		return
	DB_manager.Polls_vote(Polls_table, Poll_ID, User_infos["Pseudo"], Choice)
	Question = Poll_infos["Question"]
	Vote = Poll_infos["Choices"][Choice]
	await Gears.Send_DM(User, Context, f"Vote “{Vote}” registered for poll #{Poll_ID} ({Question})")

@polls.command(name="vote")
async def Discord_polls_vote(Context, *, Arguments):
	"""Vote in a poll.
	Parameters
	----------
	Arguments : str
		syntax: “!polls vote <Choice_number> [Poll_ID]”"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_create(Bridge, Context.author.display_name, Arguments, Context)

async def Polls_info(Bridge, Poll_ID=None, Author=None):

	Polls_table = Config["polls"]["db_table"]
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		if Poll_ID:
			Output_IRC = f"<\x02{User}\x02> !polls info {Poll_ID}\n"
		else:
			Output_IRC = f"<\x02{User}\x02> !polls info\n"
	if Poll_ID:
		try:
			Poll_ID = int(Poll_ID)
			# To avoid a DB query later, if the lastest poll has been automatically selected
			Poll_infos = None
		except (TypeError, ValueError):
			Output += "Error: invalid poll ID."
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
	# If no poll ID was given, automatically select the lastest
	else:
		Poll_infos = DB_manager.Polls_fetch_last(Polls_table)
		if not Poll_infos:
			Output += "Error: no polls in the DB."
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
		Poll_ID = Poll_infos["ID"]
	# Avoid a DB query, in case the lastest poll was automatically selected
	if not Poll_infos:
		Poll_infos = DB_manager.Polls_fetch(Polls_table, Poll_ID)
	if not Poll_infos:
		Output += f"Error: poll #{Poll_ID} doesn’t exist."
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return

	Status = "active" if Poll_infos["Active"] else "closed"
	Creation_date = datetime.datetime.strftime(Poll_infos["Creation_date"], "%d/%m/%Y")
	Number_of_voters = 0
	Votes_for_each_choice = {}
	Result_count = 0
	for Choice_ID in Poll_infos["Choices"]:
		Votes_for_each_choice[Choice_ID] = []
	for Voter, Choice_ID in Poll_infos["Votes"].items():
		if Choice_ID in Votes_for_each_choice:
			Votes_for_each_choice[Choice_ID].append(Voter)
			Number_of_voters += 1
	Output += f"#{Poll_ID} created {Creation_date} by {Poll_infos['Author']} [{Status}] : "
	Output += f"{Poll_infos['Question']}\n"
	if Number_of_voters > 0:
		for Choice_ID, Choice_text in Poll_infos["Choices"].items():
			Choice_voters = Votes_for_each_choice[Choice_ID]
			Choice_count = len(Choice_voters)
			if Choice_count > 0:
				# Can’t be a division by zero since Number_of_voters > 0
				Percentage = int((Choice_count / Number_of_voters) * 100)
				Output += f"{Percentage}% {Choice_text} {Choice_count} "
				Output += "(" + " ".join(Choice_voters) + ")\n"
			if Choice_count > Result_count:
				Result_count = Choice_count
				Result_text = Choice_text
		Output += f"The result is {Result_text} with {Result_count} vote"
		if Number_of_voters > 1:
			Output += "s"
		Output += "."
	else:
		Output += f"No one has voted in this poll yet."
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="info")
async def Discord_polls_info(Context, Poll_ID=None):
	"""Display informations about a poll.
	Parameters
	----------
	Poll_ID : int
		“!polls info [Poll_ID]”"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_info(Bridge, Poll_ID, Context.author.display_name)
