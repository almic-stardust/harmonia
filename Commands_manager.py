# -*- coding: utf-8 -*-

import inspect
import random
import re
import hashlib
import datetime
from dateutil.relativedelta import relativedelta

from Config_manager import Config
import DB_manager
import Gears
import Discord_manager
from Discord_manager import bot
import IRC_manager

Straws_bag = {}
Straws_bag["Common_key"] = {}
Straws_bag["Users"] = []
Proxies = {}

###############################################################################
# Dispatch IRC commands
###############################################################################

async def IRC_dispatcher(Bridge, User, Text):

	# The IRC_* functions are used when it’s necessary to handle arguments specifically for IRC
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
			"list":			(Polls_list,				True,			False),
			"proxy":		(Polls_proxy,				True,			True),
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
		Output = "Invalid command. See !help"
		Output_IRC = Output + " (on Discord)"
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
			Output = f"Invalid subcommand. See !help {Command}"
			Output_IRC = Output + " (on Discord)"
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
		!roll NdN"""
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
			Output += f"<{User}> {Straws_bag['Common_key'][User]}\n"

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
		Help_usage = "See !help straws"
		Output += Help_usage
		Output_IRC += Help_usage + " (on Discord)"
	await Gears.Send(Bridge, Output, Output_IRC)

@bot.group()
async def straws(Context):
	"""Draw straws among a group, with a reproducible pseudo-randomness."""
	if Context.invoked_subcommand is None:
		# If there’s something after “!straws”, but it’s not a valid subcommand
		if Context.subcommand_passed is not None:
			await Context.send("Invalid subcommand. See !help straws")
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
	Output = "See !help straws"
	Output_IRC += Output + " (on Discord)"
	await Gears.Send(Bridge, Output, Output_IRC)

@straws.command(name="help")
async def Discord_straws_help(Context):
	"""Placeholder redirecting towards !help straws"""
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
		!straws participate Word"""
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
		!straws contribute Word"""
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
		!straws users User1 [User2] […]"""
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
		Output = "No participants between whom to draw. See !help straws"
		Output_IRC += Output + " (on Discord)"
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	if len(Straws_bag["Common_key"]) == 0:
		Output = "No straws to draw from. See !help straws"
		Output_IRC += Output + " (on Discord)"
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
		Output += f"<{User}> {Beginning_hash}[…]\n"
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
			await Context.send("Invalid subcommand. See !help polls")
			return
		# If no subcommand is invoked: “!polls” = “!polls list”
		Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
		if Bridge:
			# Polls_list(Bridge, Arguments=None, Author=None):
			await Polls_list(Bridge, None, Context.author.display_name)

async def IRC_polls(Bridge):
	await Polls_list(Bridge)

async def Polls_help(Bridge, Author=None):
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		Output_IRC = f"<\x02{Author}\x02> !polls help\n"
	Output = "See !help polls"
	Output_IRC += Output + " (on Discord)"
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="help")
async def Discord_polls_help(Context):
	"""Placeholder redirecting towards !help polls"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_help(Bridge, Context.author.display_name)

def Polls_voting_rights(Infos_user):
	Infos_user["Can_vote"] = False
	if not Infos_user["Renewals"]:
		return Infos_user
	Renewals_years = []
	Renewals_dates = []
	for Year in Infos_user["Renewals"]:
		Renewals_years.append(Year)
		Renewals_dates.extend(Infos_user["Renewals"][Year])
	Renewals_years.sort()
	Renewals_dates.sort()
	Infos_user["Registration"] = Renewals_dates[0]
	Infos_user["Last_renewal"] = Renewals_dates[-1]
	Infos_user["Penultimate_year"] = None
	if len(Renewals_years) >= 2:
		Penultimate_year = Renewals_years[-2]
		Infos_user["Penultimate_year"] = datetime.datetime.strptime(str(Penultimate_year), "%Y")
	Now = datetime.datetime.now()
	# relativedelta rather than timedelta, to calculate voting rights with calendar years and months
	Has_one_year_membership = Infos_user["Registration"] <= Now - relativedelta(years=1)
	Renewal_within_last_year = Infos_user["Last_renewal"] >= Now - relativedelta(years=1)
	# Current membership
	if Has_one_year_membership and Renewal_within_last_year:
		Infos_user["Can_vote"] = True
	# Former member who renewed their membership in the year, but more than 3 months ago
	elif Infos_user["Penultimate_year"]:
		Penultimate_over_1y = Infos_user["Penultimate_year"] >= Now - relativedelta(years=1)
		Renewal_over_3m = Infos_user["Last_renewal"] >= Now - relativedelta(months=3)
		if Penultimate_over_1y and Renewal_within_last_year and Renewal_over_3m:
			Infos_user["Can_vote"] = True
	return Infos_user

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
			Infos_user = {}
			Infos_user["Pseudo"] = User
			User_ID = DB_manager.Users_check_presence(Users_table, Infos_user)
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
		Infos_user = Users_to_display[User_ID]
		Infos_user = Polls_voting_rights(Infos_user)
		if Infos_user["Can_vote"]:
			Output += f"{Infos_user['Pseudo']} "
		# If we display all voting members, keep a concise display
		if not List_of_users_from_argument:
			continue
		if Infos_user["Can_vote"]:
			Output += f"can vote "
		else:
			Output += f"{Infos_user['Pseudo']} can’t vote "
		Registration = datetime.datetime.strftime(Infos_user["Registration"], "%d/%m/%Y")
		Last_renewal = datetime.datetime.strftime(Infos_user["Last_renewal"], "%d/%m/%Y")
		if Infos_user["Penultimate_year"]:
			Penultimate_year = datetime.datetime.strftime(Infos_user["Penultimate_year"], "%Y")
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
		(optional) !straws members [Member1 Member2 …]"""
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
		Output += "Usage: !polls create Subject [§ Choice 1 ; Choice 2 ; …]"
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	if "§" in Arguments:
		Question, Choices = Arguments.split("§", 1)
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
	Output += f"Poll {Poll_ID}: {Question}\n["
	for Index, Choice in enumerate(Choices):
		Output += f"#{Index + 1} {Choice}"
		if Index + 1 < len(Choices):
			Output += "] ["
		else:
			Output += "]\n"
	Output += f"Vote with: !polls vote <Choice_number> [{Poll_ID}]"
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="create")
async def Discord_polls_create(Context, *, Arguments):
	"""Create a new poll.
	Parameters
	----------
	Arguments : str
		syntax: !polls create Subject [§ Choice 1 ; Choice 2 ; …]"""
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
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			Output += "Error: no polls in the DB."
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
		Polls_IDs.append(Infos_poll["ID"])
	else:
		# To avoid a DB query later, if the lastest poll has been automatically selected
		Infos_poll = None
		for Poll_ID in Arguments.split():
			try:
				Polls_IDs.append(int(Poll_ID))
			except (TypeError, ValueError):
				Output += f"Error: {Poll_ID} is an invalid poll ID.\n"
				continue

	for Poll_ID in Polls_IDs:
		# Avoid a DB query, in case the lastest poll was automatically selected
		if len(Polls_IDs) > 1 or (len(Polls_IDs) == 1 and not Infos_poll):
			Infos_poll = DB_manager.Polls_fetch(Polls_table, Poll_ID)
		if not Infos_poll:
			Output += f"Error: poll #{Poll_ID}: doesn’t exist.\n"
			continue
		if not Infos_poll["Active"]:
			Output += f"Error: poll #{Poll_ID}: already closed.\n"
			continue
		# Moderators can also close polls
		if not (User == Infos_poll["Author"] or Is_moderator):
			Output += f"Error: poll #{Poll_ID}: only the author or a moderator can close a poll.\n"
			continue
		DB_manager.Polls_close(Polls_table, Poll_ID)
		Output += f"{User} closed poll #{Poll_ID} ({Infos_poll['Question']})\n"
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="close")
async def Discord_polls_close(Context, *, Arguments=None):
	"""Close one or several poll (the latest if no ID is specified).
	Parameters
	----------
	Arguments : int
		syntax: !polls close [Poll_ID] [Poll_ID] […]"""
	Is_moderator = Context.author.guild_permissions.manage_messages
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_close(Bridge, Context.author.display_name, Is_moderator, Arguments, True)

async def IRC_polls_close(Bridge, User, Arguments=None):
	Is_user_op = IRC_manager.Is_op(Bridge["irc_chan"], User)
	await Polls_close(Bridge, User, Is_user_op, Arguments)

async def Polls_vote(Bridge, User, Arguments, Context=None):

	global Proxies
	Users_table = Config["users"]["db_table"]
	Polls_table = Config["polls"]["db_table"]
	IRC_instance = IRC_manager.GCI()
	# If the command was sent on Discord, relay it on IRC
	# No usage of Output_IRC for this function, because user related errors are sent privately
	if Context:
		if IRC_instance:
			await IRC_instance.Relay_Discord_message(Bridge["irc_chan"], User,
					f"<\x02{User}\x02> !polls vote {Arguments}"
			)
	Help_usage = "Usage: !polls vote <Choice_number> [Poll_ID]"
	if not Arguments:
		await Gears.Send(Bridge, Help_usage)
		return

	Parts = Arguments.split()
	Proxy_giver = None
	# If the user casts a different vote for one of their proxies giver
	if len(Parts) == 3:
		Claimed_proxy_giver = Parts[2]
		if Claimed_proxy_giver in Proxies[User]:
			Proxy_giver = Claimed_proxy_giver
		else:
			await Gears.Send(Bridge,
					f"Error: {Claimed_proxy_giver} didn’t delegate a proxy to {User}."
			)
	if len(Parts) == 2 or (len(Parts) == 3 and Proxy_giver):
		try:
			Choice = int(Parts[0])
			Poll_ID = int(Parts[1])
			# To avoid a DB query later, if the lastest poll has been automatically selected
			Infos_poll = None
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
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			await Gears.Send(Bridge, "Error: no polls in the DB.")
			return
		Poll_ID = Infos_poll["ID"]
	else:
		await Gears.Send(Bridge, Help_usage)
		return

	Infos_user = {"Pseudo": User}
	User_ID = DB_manager.Users_check_presence(Users_table, Infos_user)
	if not User_ID:
		await Gears.Send_DM(User, Context, "Error: you’re not registered.")
		return
	Users = DB_manager.Users_fetch_users(Users_table)
	Infos_user = Users[User_ID]
	Infos_user = Polls_voting_rights(Infos_user)
	if not Infos_user["Can_vote"]:
		await Gears.Send_DM(User, Context, "Error: you don’t have voting rights.")
		return
	# Avoid a DB query, in case the lastest poll was automatically selected
	if not Infos_poll:
		Infos_poll = DB_manager.Polls_fetch(Polls_table, Poll_ID)
	if not Infos_poll:
		await Gears.Send(Bridge, "Error: poll not found. See !polls list")
		return
	if not Infos_poll["Active"]:
		await Gears.Send(Bridge, f"Error: poll #{Poll_ID} is closed. See !polls list active")
		return
	Choices = Infos_poll["Choices"]
	if Choice < 1 or Choice > len(Choices):
		await Gears.Send(Bridge, f"Error: invalid choice number. See !polls info {Poll_ID}")
		return

	Recorded_in_DB = False
	Question = Infos_poll["Question"]
	Vote_text = Choices[Choice]
	if Proxy_giver:
		Recorded_in_DB = DB_manager.Polls_vote(
				Polls_table, Poll_ID, Proxy_giver, Choice, User
		)
		if Recorded_in_DB:
			await Gears.Send_DM(User, Context,
					f"Poll #{Poll_ID}: Vote “{Vote_text}” registered for {Proxy_giver} [{Question}]"
			)
	else:
		# {Infos_user["Pseudo"]} instead of {User}, to see in the results if the bot mistakes users
		Recorded_in_DB = DB_manager.Polls_vote(
				Polls_table, Poll_ID, Infos_user["Pseudo"], Choice
		)
		if Recorded_in_DB:
			await Gears.Send_DM(User, Context,
					f"Poll #{Poll_ID}: Your vote “{Vote_text}” has been registered [{Question}]"
			)
		# Those who have delegated a proxy vote by default as their proxy holder
		if User in Proxies:
			for Proxy_giver in Proxies[User]:
				Recorded_in_DB = False
				Recorded_in_DB = DB_manager.Polls_vote(
						Polls_table, Poll_ID, Proxy_giver, Choice, User
				)
				if Recorded_in_DB:
					await Gears.Send_DM(User, Context,
							f"Poll #{Poll_ID}: Vote “{Vote_text}” registered for {Proxy_giver} [{Question}]"
					)

@polls.command(name="vote")
async def Discord_polls_vote(Context, *, Arguments):
	"""Vote in a poll.
	Parameters
	----------
	Arguments : str
		syntax: !polls vote <Choice_number> [Poll_ID]"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_create(Bridge, Context.author.display_name, Arguments, Context)

async def Polls_proxy_delegate(Bridge, User, Context, Proxy_holder, Proxy_giver):

	global Proxies
	Users_table = Config["users"]["db_table"]
	Polls_table = Config["polls"]["db_table"]
	Change_of_holder = False
	# No self-proxy
	if User == Proxy_holder:
		await Gears.Send_DM(User, Context, "Error: a member cannot delegate to themselves.")
		return

	# Only members with voting rights can delegate a proxy
	Infos_user = {}
	Infos_user["Pseudo"] = User
	User_ID = DB_manager.Users_check_presence(Users_table, Infos_user)
	if not User_ID:
		await Gears.Send_DM(User, Context, "Error: you’re not registered.")
		return
	Users = DB_manager.Users_fetch_users(Users_table)
	Infos_user = Users[User_ID]
	Infos_user = Polls_voting_rights(Infos_user)
	if not Infos_user["Can_vote"]:
		await Gears.Send_DM(User, Context, "Error: you don’t have voting rights.")
		return

	# Only members with voting rights can receive proxies
	Infos_holder = {}
	Infos_holder["Pseudo"] = Proxy_holder
	Holder_ID = DB_manager.Users_check_presence(Users_table, Infos_holder)
	if not Holder_ID:
		await Gears.Send_DM(User, Context, f"{Proxy_holder} isn’t registered.")
		return
	Infos_holder = Users[Holder_ID]
	Infos_holder = Polls_voting_rights(Infos_holder)
	if not Infos_holder["Can_vote"]:
		await Gears.Send_DM(User, Context, f"{Proxy_holder} don’t have voting rights.")
		return

	Now = datetime.datetime.now(datetime.timezone.utc)
	for Old_holder in Proxies:
		if User in Proxies[Old_holder]:
			if Old_holder == Proxy_holder:
				await Gears.Send_DM(User, Context,
						f"You’ve already delegated your proxy to {Proxy_holder}."
				)
				return
			# Proxies are valid for a complete meeting (approximated to 12 hours)
			Proxy_duration = Now - Proxies[Old_holder][User]
			if Proxy_duration < datetime.timedelta(hours=12):
				# A member can only have one proxy holder
				del Proxies[Old_holder][User]
				Change_of_holder = True
	if Proxy_holder not in Proxies:
		Proxies[Proxy_holder] = {}
	# Each member can receive a proxy from a maximum of 3 members
	if len(Proxies[Proxy_holder]) >=3:
		await Gears.Send(Bridge, f"{Proxy_holder} already holds 3 proxies.")
		return
	Proxies[Proxy_holder][User] = Now
	Output = f"{User} delegated their proxy to {Proxy_holder}"
	if Change_of_holder:
		Output += f" (previously to {Old_holder})"
	Output += "."
	await Gears.Send(Bridge, Output)

async def Polls_proxy(Bridge, User, Arguments, Context=None):

	IRC_instance = IRC_manager.GCI()
	# If the command was sent on Discord, relay it on IRC
	# No usage of Output_IRC for this function, because user related errors are sent privately
	if Context:
		if IRC_instance:
			await IRC_instance.Relay_Discord_message(
					Bridge["irc_chan"], User, f"!polls proxy {Proxy_holder}"
			)
	Help_usage = "Usage: !polls proxy delegate Proxy_holder [Member] | !polls proxy list Member | !polls proxy revoke [all]"""
	if not Arguments:
		await Gears.Send(Bridge, "Error: invalid syntax.\n" + Help_usage)
		return
	if Arguments:
		Parts = Arguments.split()
		if len(Parts) < 0 or Parts[0] not in ("delegate", "list", "revoke"):
			await Gears.Send(Bridge, "Error: invalid syntax.\n" + Help_usage)
			return
	Action = Parts[0]

	if Action == "delegate":
		if len(Parts) < 2 or len(Parts) > 3:
			await Gears.Send(Bridge, "Error: invalid syntax.\n" + Help_usage)
			return
		Proxy_holder = Parts[1]
		Proxy_giver = None
		if len(Parts) == 3:
			Proxy_giver = Parts[2]
		await Polls_proxy_delegate(Bridge, User, Context, Proxy_holder, Proxy_giver)

@polls.command(name="proxy")
async def Discord_polls_proxy(Context, *, Arguments):
	"""Manage votes by proxy.\n
	 \n
	!polls proxy delegate Holder [Member]\n
	!polls proxy list Member\n
	!polls proxy revoke [all]
	Parameters
	----------
	Arguments : str"""

	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_proxy(Bridge, User, Arguments, Context)

async def Polls_info(Bridge, Poll_ID=None, Author=None):

	Polls_table = Config["polls"]["db_table"]
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		if Poll_ID:
			Output_IRC = f"<\x02{Author}\x02> !polls info {Poll_ID}\n"
		else:
			Output_IRC = f"<\x02{Author}\x02> !polls info\n"
	if Poll_ID:
		try:
			Poll_ID = int(Poll_ID)
			# To avoid a DB query later, if the lastest poll has been automatically selected
			Infos_poll = None
		except (TypeError, ValueError):
			Output += "Error: invalid poll ID."
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
	# If no poll ID was given, automatically select the lastest
	else:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			Output += "Error: no polls in the DB."
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
		Poll_ID = Infos_poll["ID"]
	# Avoid a DB query, in case the lastest poll was automatically selected
	if not Infos_poll:
		Infos_poll = DB_manager.Polls_fetch(Polls_table, Poll_ID)
	if not Infos_poll:
		Output += f"Error: poll #{Poll_ID} doesn’t exist."
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return

	Creation_date = datetime.datetime.strftime(Infos_poll["Creation_date"], "%d/%m/%Y")
	Choices = Infos_poll["Choices"]
	Status = "active" if Infos_poll["Active"] else "closed"
	Number_of_voters = 0
	Votes_for_each_choice = {}
	Result_count = 0
	for Choice_ID in Choices:
		Votes_for_each_choice[Choice_ID] = []
	for Voter, Choice_ID in Infos_poll["Votes"].items():
		if Choice_ID in Votes_for_each_choice:
			Votes_for_each_choice[Choice_ID].append(Voter)
			Number_of_voters += 1
	Output += f"Poll {Poll_ID} created {Creation_date} by {Infos_poll['Author']} ({Status}) : "
	Output += f"{Infos_poll['Question']}\n"
	if Number_of_voters > 0:
		Output_for_voters = ""
		Choices_without_votes = []
		for Choice_ID, Choice_text in Choices.items():
			Choice_voters = Votes_for_each_choice[Choice_ID]
			Choice_count = len(Choice_voters)
			if Choice_count > 0:
				# Can’t be a division by zero since Number_of_voters > 0
				Percentage = int((Choice_count / Number_of_voters) * 100)
				Output_for_voters += f"{Percentage}% #{Choice_ID} {Choice_text} ({Choice_count} = "
				Output_for_voters += ", ".join(Choice_voters) + ")\n"
				if Choice_count > Result_count:
					Result_count = Choice_count
					Result_text = Choice_text
			else:
				Choices_without_votes.append([Choice_ID, Choice_text])
		if len(Choices_without_votes) > 0:
			Output += "Choices without votes: ["
			Index = 0
			for Choice_ID, Choice_text in Choices_without_votes:
				Index += 1
				Output += f"#{Choice_ID} {Choice_text}"
				if Index < len(Choices_without_votes):
					Output += "] ["
				else:
					Output += "]\n"
		Output += Output_for_voters
		Output += f"The result is “{Result_text}”, with {Result_count} vote"
		if Result_count > 1:
			Output += "s"
		Output += f" out of {Number_of_voters}."
	else:
		Output += f"No one has voted in this poll yet."
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="info")
async def Discord_polls_info(Context, Poll_ID=None):
	"""Display informations about a poll.
	Parameters
	----------
	Poll_ID : int
		!polls info [Poll_ID]"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_info(Bridge, Poll_ID, Context.author.display_name)

async def Polls_list(Bridge, Arguments=None, Author=None):
	Polls_table = Config["polls"]["db_table"]
	Status = None
	Number = None
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if Author:
		if Arguments:
			Output_IRC = f"<\x02{Author}\x02> !polls list {Arguments}\n"
		else:
			Output_IRC = f"<\x02{Author}\x02> !polls list\n"
	Help_usage = "Usage: !polls list [Number] | !polls list [active/closed] [Number]"""
	if Arguments:
		Parts = Arguments.split()
		if len(Parts) > 2:
			Output = "Error: invalid syntax.\n" + Help_usage
			Output_IRC += Output
			await Gears.Send(Bridge, Help_usage, Output_IRC)
			return
		if Parts[0] in ("active", "closed"):
			Status = Parts[0]
			if len(Parts) == 2:
				Number = Parts[1]
		# If the first argument isn’t "active" or "closed", then it should be the number of polls
		else:
			Number = Parts[0]
	if Number:
		try:
			Number = int(Number)
		except (TypeError, ValueError):
			Output += "Error: invalid poll ID. " + Help_usage
			Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
	# If the number of polls is not specified, display the last 3
	if not Number:
		Number = 3
	if Number > 10:
		Number = 10
	Polls = DB_manager.Polls_fetch_list(Polls_table, Number, Status)
	if not Polls:
		Output += "Error: no polls in the DB."
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	for Infos_poll in Polls:
		Status = "active" if Infos_poll["Active"] else "closed"
		Output += f"#{Infos_poll['ID']} ({Status}) {Infos_poll['Question']}\n"
	Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="list")
async def Discord_polls_list(Context, *, Arguments=None):
	"""Display a list of polls (10 max | no number given = last 3 polls).
	Parameters
	----------
	Arguments : str
		syntax: !polls list [Number] | !polls list [active/closed] [Number]"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_list(Bridge, Arguments, Context.author.display_name)
