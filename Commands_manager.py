# -*- coding: utf-8 -*-
# “Commands” is susceptible to be a keyword used elsewhere → this file is named Commands_manager.py

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

IRC_enabled = Config["enabled_sections"]["irc"]
if IRC_enabled:
	import IRC_manager
Users_enabled = Config["enabled_sections"]["users"]
if Users_enabled:
	Users_table = Config["users"]["db_table"]
Polls_enabled = Config["enabled_sections"]["polls"]
if Polls_enabled:
	Polls_table = Config["polls"]["db_table"]
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
			"delete":		(IRC_polls_delete,			True,			True),
			"vote":			(Polls_vote,				True,			True),
			"unvote":		(Polls_unvote,				True,			True),
			"info":			(Polls_info,				True,			False),
			"list":			(Polls_list,				True,			False),
			"proxy":		(IRC_polls_proxy,			True,			True),
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
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC. Otherwise, IRC users will see a
		# response from the bot, without seeing the command that prompted it.
		if Author:
			Output_IRC = f"<\x02{Author}\x02> !roll {Dice}\n"
	try:
		# Accept NDN as well as NdN
		Dice = Dice.lower()
		Number_rolls, Faces = map(int, Dice.split("d"))
		if Faces > 100:
			await Gears.Send(Bridge, "Error: dice faces are limited to 100.")
			return
		Rolls = []
		for _ in range(Number_rolls):
			Roll = random.randint(1, Faces)
			Rolls.append(Roll)
		Output = ", ".join(map(str, Rolls))
		if Number_rolls > 10:
			Min = min(Rolls)
			Max = max(Rolls)
			Total = sum(Rolls)
			Average = Total / Number_rolls
			Summary = f"Min {Min} | Average {Average:.1f} | Max {Max} | Total {Total}"
			if Number_rolls <= 100:
				Output += "\n" + Summary
			else:
				Output = Summary
	except Exception as Error:
		print(f"[Commands] Roll_Dice(): {Error}")
		Output = "Format has to be NdN."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@bot.command()
async def roll(Context, Dice):
	"""Roll Dice in NdN format.\n
	 \n
	!roll NdN
	Parameters
	----------
	Dice : str"""
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
	if IRC_enabled:
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
		for User, Straw in Straws_bag["Common_key"].items():
			Output += f"<{User}> {Straw}\n"

	if not Presence_participants:
		Display_help = True
		if Presence_straws:
			Output += "\nBut no participants between whom to draw. "
		else:
			Output += "No participants between whom to draw, and the bag is empty.\n"
	if Presence_participants and not Presence_straws:
		Display_help = True
		Output += "But the bag is empty. "
	if IRC_enabled:
		Output_IRC += Output
	if Display_help:
		Help_usage = "See !help straws"
		Output += Help_usage
		if IRC_enabled:
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
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if Author:
			Output_IRC = f"<\x02{Author}\x02> !straws help\n"
	Output = "See !help straws"
	if IRC_enabled:
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
	if IRC_enabled:
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
		if IRC_enabled and IRC_instance:
			await IRC_instance.Safe_message(User, Output)

@straws.command(name="participate")
async def Discord_straws_participate(Context, *, Word):
	"""Put a straw in the bag (and participate in the draw).\n
	 \n
	!straws participate Word
	Parameters
	----------
	Word : str"""
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
	"""Put a straw in the bag (without participating in the draw).\n
	 \n
	!straws contribute Word
	Parameters
	----------
	Word : str"""
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
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if Author:
			Output_IRC = f"<\x02{Author}\x02> !straws users {Users}\n"
	if len(Users) > 50:
		Output = "The draw is limited to 50 users."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Straws_bag["Users"] = []
	for User in Users.split():
		Straws_bag["Users"].append(User[:30])
	Output = "The list of users has been set (usernames are limited to 30 characters)."
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@straws.command(name="users")
async def Discord_straws_users(Context, *, Users):
	"""Set the list of users participating in the draw.\n
	 \n
	!straws users User1 [User2] […]
	Parameters
	----------
	Users : str"""
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
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if Author:
			Output_IRC = f"<\x02{Author}\x02> !straws draw\n"
	if len(Straws_bag["Users"]) == 0:
		Output = "No participants between whom to draw. See !help straws"
		if IRC_enabled:
			Output_IRC += Output + " (on Discord)"
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	if len(Straws_bag["Common_key"]) == 0:
		Output = "No straws to draw from. See !help straws"
		if IRC_enabled:
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
	if IRC_enabled:
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
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if Author:
			Output_IRC = f"<\x02{Author}\x02> !straws reset\n"
	Straws_bag["Common_key"] = {}
	Straws_bag["Users"] = []
	Output = "The list of participants has been deleted, and the bag is now empty."
	if IRC_enabled:
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
			await Polls_list(Bridge, None, Context.author.display_name)

async def IRC_polls(Bridge):
	await Polls_list(Bridge)

async def Polls_help(Bridge, Author=None):
	Output_IRC = ""
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if Author:
			Output_IRC = f"<\x02{Author}\x02> !polls help\n"
	Output = "See !help polls"
	if IRC_enabled:
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
	Unregistered = []
	Output = ""
	Output_IRC = ""
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if Author:
			if List_of_users:
				Output_IRC = f"<\x02{Author}\x02> !polls members {List_of_users}\n"
			else:
				Output_IRC = f"<\x02{Author}\x02> !polls members\n"
	if not Users_enabled:
		Output = "Error: This command requires the users section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Users = DB_manager.Users_fetch_users(Users_table)
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
			if IRC_enabled:
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
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="members")
async def Discord_polls_members(Context, *, Members=None):
	"""Display informations about members’ voting rights.\n
	 \n
	!straws members [Member1 Member2 …]
	Parameters
	----------
	Members : str"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		# In the !help for this subcommand, it’s better to display Members instead of List_of_users
		await Polls_members(Bridge, Members, Context.author.display_name)

async def Polls_create(Bridge, User, Arguments, From_Discord=False):
	Output = ""
	Output_IRC = ""
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if From_Discord:
			Output_IRC = f"<\x02{User}\x02> !polls create {Arguments}\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	if not Arguments:
		Output += "Usage: !polls create Subject [§ Choice 1 ; Choice 2 ; …]"
		if IRC_enabled:
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
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
	else:
		Choices = ["Yes", "No"]
	Poll_ID = DB_manager.Polls_create(Polls_table, User, Question, Choices)
	Output += f"Poll {Poll_ID}: {Question}\n[#0 Blank] ["
	for Index, Choice in enumerate(Choices):
		Output += f"#{Index + 1} {Choice}"
		if Index + 1 < len(Choices):
			Output += "] ["
		else:
			Output += "]\n"
	Output += f"Vote with: !polls vote <Choice_number> [{Poll_ID}]"
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="create")
async def Discord_polls_create(Context, *, Arguments):
	"""Create a new poll.\n
	 \n
	!polls create Subject [§ Choice 1 ; Choice 2 ; …]
	Parameters
	----------
	Arguments : str"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_create(Bridge, Context.author.display_name, Arguments, True)

async def Polls_close(Bridge, User, Is_moderator, Arguments, From_Discord=False):

	Polls_IDs = []
	Output = ""
	Output_IRC = ""
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if From_Discord:
			if Arguments:
				Output_IRC = f"<\x02{User}\x02> !polls close {Arguments}\n"
			else:
				Output_IRC = f"<\x02{User}\x02> !polls close\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return

	# Select latest poll if none specified
	if not Arguments:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			Output += "Error: no polls in the DB."
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
		Polls_IDs.append(Infos_poll["ID"])
	else:
		# To avoid a DB query in the other case, when the lastest poll is automatically selected
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
			Output += f"Error: poll {Poll_ID}: doesn’t exist.\n"
			continue
		if not Infos_poll["Active"]:
			Output += f"Error: poll {Poll_ID}: already closed.\n"
			continue
		# Moderators can also close polls
		if User == Infos_poll["Author"] or Is_moderator:
			Recorded_in_DB = False
			Recorded_in_DB = DB_manager.Polls_close(Polls_table, Poll_ID)
			if Recorded_in_DB:
				Output += f"{User} closed poll {Poll_ID} ({Infos_poll['Question']})\n"
		else:
			Output += f"Error: poll {Poll_ID}: only the author or a moderator can close a poll.\n"
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="close")
async def Discord_polls_close(Context, *, Arguments=None):
	"""Close one or several poll (the latest if no ID is specified).\n
	 \n
	!polls close [Poll_ID] [Poll_ID] […]
	Parameters
	----------
	Arguments : int"""
	Is_moderator = Context.author.guild_permissions.manage_messages
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_close(Bridge, Context.author.display_name, Is_moderator, Arguments, True)

async def IRC_polls_close(Bridge, User, Arguments=None):
	# If this function is called, IRC_manager will have been imported 
	Is_user_op = IRC_manager.Is_op(Bridge["irc_chan"], User)
	await Polls_close(Bridge, User, Is_user_op, Arguments)

async def Polls_delete(Bridge, User, Is_moderator, Arguments, From_Discord=False):

	Polls_IDs = []
	Output = ""
	Output_IRC = ""
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if From_Discord:
			if Arguments:
				Output_IRC = f"<\x02{User}\x02> !polls delete {Arguments}\n"
			else:
				Output_IRC = f"<\x02{User}\x02> !polls delete\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return

	# Select latest poll if none specified
	if not Arguments:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			Output += "Error: no polls in the DB."
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
		Polls_IDs.append(Infos_poll["ID"])
	else:
		# To avoid a DB query in the other case, when the lastest poll is automatically selected
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
			Output += f"Error: poll {Poll_ID}: doesn’t exist or was already deleted.\n"
			continue
		# Moderators can also delete polls
		if User == Infos_poll["Author"] or Is_moderator:
			Recorded_in_DB = False
			Recorded_in_DB = DB_manager.Polls_delete(Polls_table, Poll_ID)
			if Recorded_in_DB:
				Output += f"{User} deleted poll {Poll_ID} ({Infos_poll['Question']})\n"
		else:
			Output += f"Error: poll {Poll_ID}: only the author or a moderator can delete a poll.\n"
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="delete")
async def Discord_polls_delete(Context, *, Arguments=None):
	"""Delete one or several poll (the latest if no ID is specified).\n
	 \n
	!polls delete [Poll_ID] [Poll_ID] […]
	Parameters
	----------
	Arguments : int"""
	Is_moderator = Context.author.guild_permissions.manage_messages
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_delete(Bridge, Context.author.display_name, Is_moderator, Arguments, True)

async def IRC_polls_delete(Bridge, User, Arguments=None):
	Is_user_op = IRC_manager.Is_op(Bridge["irc_chan"], User)
	await Polls_delete(Bridge, User, Is_user_op, Arguments)

async def Polls_vote(Bridge, User, Arguments, Context=None):

	global Proxies
	if IRC_enabled:
		IRC_instance = IRC_manager.GCI()
		# If the command was sent on Discord, relay it on IRC
		# No usage of Output_IRC for this function, because user related errors are sent privately
		if Context:
			if IRC_instance:
				await IRC_instance.Relay_Discord_message(Bridge["irc_chan"], User,
						f"<\x02{User}\x02> !polls vote {Arguments}"
				)
	if not Polls_enabled:
		await Gears.Send(Bridge,
				"Error: This command requires the polls section to be enabled in the config file."
		)
		return
	if not Users_enabled:
		await Gears.Send(Bridge,
				"Error: This command requires the users section to be enabled in the config file."
		)
		return
	Help_usage = "Usage: !polls vote <Choice_number> [Poll_ID]"
	if not Arguments:
		await Gears.Send(Bridge, Help_usage)
		return

	Parts = Arguments.split()
	Proxy_giver = None
	# If the user casts a different vote for one of their proxies giver
	if len(Parts) == 3:
		Claimed_proxy_giver = Parts[2]
		# For Claimed_proxy_giver to have delegated a proxy to User, User must have received at
		# least one proxy in the first space
		if User in Proxies and Claimed_proxy_giver in Proxies[User]:
			Proxy_giver = Claimed_proxy_giver
		else:
			await Gears.Send(Bridge,
					f"Error: {Claimed_proxy_giver} didn’t delegate a proxy to {User}."
			)
	if len(Parts) == 2 or (len(Parts) == 3 and Proxy_giver):
		try:
			# Consistency over intuition: the first argument is always Choice
			Choice = int(Parts[0])
			Poll_ID = int(Parts[1])
			# To avoid a DB query in the other case, when the lastest poll is automatically selected
			Infos_poll = None
		except ValueError:
			await Gears.Send(Bridge, f"Error: invalid poll ID or choice number.\n" + Help_usage)
			return
	# Select latest poll if none specified
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
		await Gears.Send(Bridge, f"Error: poll {Poll_ID} is closed. See !polls list active")
		return
	Choices = Infos_poll["Choices"]
	if Choice < 0 or Choice > len(Choices):
		await Gears.Send(Bridge, f"Error: invalid choice number. See !polls info {Poll_ID}")
		return

	# If a member votes in a poll, it automatically revokes any proxy they may have given
	Handler_to_revoke = None
	for Proxy_holder in Proxies:
		for Proxy_given_to_holder in Proxies[Proxy_holder]:
			if Proxy_given_to_holder == User:
				Handler_to_revoke = Proxy_holder
	if Handler_to_revoke:
		del Proxies[Proxy_holder][User]
		if len(Proxies[Proxy_holder]) == 0:
			del Proxies[Proxy_holder]
		await Gears.Send_DM(User, Context,
			f"Your vote has revoked the proxy delegated to {Proxy_holder}."
		)

	Recorded_in_DB = False
	Question = Infos_poll["Question"]
	if Choice == 0:
		Vote_text = "Blank"
	else:
		Vote_text = Choices[Choice]
	if Proxy_giver:
		Recorded_in_DB = DB_manager.Polls_vote(
				Polls_table, Poll_ID, Proxy_giver, Choice, User
		)
		if Recorded_in_DB:
			await Gears.Send_DM(User, Context,
					f"Poll {Poll_ID}: Vote “{Vote_text}” registered for {Proxy_giver} [{Question}]"
			)
	else:
		# {Infos_user["Pseudo"]} instead of {User}, to see user misidentifications in the results
		Recorded_in_DB = DB_manager.Polls_vote(
				Polls_table, Poll_ID, Infos_user["Pseudo"], Choice
		)
		if Recorded_in_DB:
			await Gears.Send_DM(User, Context,
					f"Poll {Poll_ID}: Your vote “{Vote_text}” has been registered [{Question}]"
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
							f"Poll {Poll_ID}: Vote “{Vote_text}” registered for {Proxy_giver} [{Question}]"
					)

@polls.command(name="vote")
async def Discord_polls_vote(Context, *, Arguments):
	"""Vote in a poll.\n
	 \n
	!polls vote <Choice_number> [Poll_ID]\n
	 \n
	“!polls vote [Poll_ID] <Choice_number>” would be more intuitive, but less consistent than having Choice_number always the first argument after vote.
	Parameters
	----------
	Arguments : str"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_vote(Bridge, Context.author.display_name, Arguments, Context)

async def Polls_unvote(Bridge, User, Poll_ID=None, Context=None):
	if IRC_enabled:
		IRC_instance = IRC_manager.GCI()
		# If the command was sent on Discord, relay it on IRC
		# No usage of Output_IRC for this function, because user related errors are sent privately
		if Context:
			if IRC_instance:
				if Poll_ID:
					Output = f"<\x02{User}\x02> !polls unvote {Poll_ID}\n"
				else:
					Output = f"<\x02{User}\x02> !polls unvote\n"
				await IRC_instance.Relay_Discord_message(Bridge["irc_chan"], User, Output)
	if not Polls_enabled:
		await Gears.Send(Bridge,
				"Error: This command requires the polls section to be enabled in the config file."
		)
		return
	if Poll_ID:
		try:
			Poll_ID = int(Poll_ID)
			# To avoid a DB query in the other case, when the lastest poll is automatically selected
			Infos_poll = None
		except (TypeError, ValueError):
			await Gears.Send(Bridge, "Error: invalid poll ID.\nUsage: !polls unvote [Poll_ID]")
			return
	# Select latest poll if none specified
	else:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			await Gears.Send(Bridge, "Error: no polls in the DB.")
			return
		Poll_ID = Infos_poll["ID"]
	# Avoid a DB query, in case the lastest poll was automatically selected
	if not Infos_poll:
		Infos_poll = DB_manager.Polls_fetch(Polls_table, Poll_ID)
	if not Infos_poll:
		await Gears.Send(Bridge, "Error: poll not found. See !polls list")
		return
	Votes = Infos_poll["Votes"]
	if User not in Votes:
		await Gears.Send_DM(User, Context, "Error: you didn’t vote in this poll.")
		return
	del Votes[User]
	Recorded_in_DB = False
	Recorded_in_DB = DB_manager.Polls_unvote(Polls_table, Poll_ID, Votes)
	if Recorded_in_DB:
		await Gears.Send(Bridge, f"{User}’s vote has been removed from poll {Poll_ID}.")

@polls.command(name="unvote")
async def Discord_polls_unvote(Context, *, Arguments):
	"""When a member wants to withdraw their participation in a poll.\n
	 \n
	!polls unvote <Choice_number> [Poll_ID]
	Parameters
	----------
	Arguments : str"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_unvote(Bridge, Context.author.display_name, Arguments, Context)

async def Polls_proxy_delegate(Bridge, Context, User, Is_moderator, Proxy_holder, Proxy_giver):

	global Proxies
	Change_of_holder = False
	# No self-proxy (“not Proxy_giver” in case User is a moderator)
	if User == Proxy_holder and not Proxy_giver:
		await Gears.Send_DM(User, Context, "Error: a member cannot delegate to themselves.")
		return
	if not Users_enabled:
		await Gears.Send(Bridge,
				"Error: This command requires the users section to be enabled in the config file."
		)
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

	if Proxy_giver:
		if Is_moderator:
			User = Proxy_giver
		else:
			await Gears.Send(Bridge,
					"Error: only moderators can delegate the proxy of someone else."
			)
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
				Change_of_holder = True
				del Proxies[Old_holder][User]
	# To be able to do checks on Proxies[Proxy_holder]
	if Proxy_holder not in Proxies:
		Proxies[Proxy_holder] = {}
	# Each member can receive a proxy from a maximum of 3 members
	if len(Proxies[Proxy_holder]) >= 3:
		await Gears.Send(Bridge, f"{Proxy_holder} already holds 3 proxies.")
		return
	Proxies[Proxy_holder][User] = Now
	Output = f"{User} delegated their proxy to {Proxy_holder}"
	if Change_of_holder:
		Output += f" (previously to {Old_holder})"

	# Simplest case: User doesn’t hold proxy to subdelegate, and Proxy_holder held up to 2 proxies.
	# Therefore by adding the proxy of User, Proxy_holder don’t exceed the limit of 3
	if not User in Proxies:
		Output += "."
		await Gears.Send(Bridge, Output)
		return
	# When User holds proxies, but Proxy_holder can’t receive any of them
	if len(Proxies[Proxy_holder]) == 3:
		Output += f" (who now hold 3 proxies), however {User} held proxies that can’t be subdelegated ("
		Output += ", ".join(Proxy for Proxy in Proxies[User])
		Output += f")."
		del Proxies[User]
		await Gears.Send(Bridge, Output)
		return
	# When User holds proxies, and Proxy_holder can receive at least some of them
	Output += f", and the following proxies were subdelegated ("
	Subdelegated = []
	for Proxy in Proxies[User]:
		if len(Proxies[Proxy_holder]) < 3:
			Proxies[Proxy_holder][Proxy] = Proxies[User][Proxy]
			Subdelegated.append(Proxy)
	Output += ", ".join(Subdelegated)
	# If the limit was reached before all proxies were subdelegated
	if len(Proxies[User]) > len(Subdelegated):
		Output += ") while the following ones couldn’t ("
		Not_subdelegated = []
		for Proxy in Proxies[User]:
			if Proxy not in Subdelegated:
				Not_subdelegated.append(Proxy)
		Output += ", ".join(Not_subdelegated)
	Output += ")."
	del Proxies[User]
	await Gears.Send(Bridge, Output)

async def Polls_proxy(Bridge, User, Is_moderator, Arguments, Context=None):

	global Proxies
	Output = ""
	if IRC_enabled:
		IRC_instance = IRC_manager.GCI()
		# If the command was sent on Discord, relay it on IRC
		# No usage of Output_IRC for this function, because user related errors are sent privately
		if Context:
			if IRC_instance:
				await IRC_instance.Relay_Discord_message(
						Bridge["irc_chan"], User, f"!polls proxy {Arguments}"
				)
	Help_usage = "Usage: !polls proxy delegate Proxy_holder [Member] | !polls proxy info Member|all | !polls proxy revoke [Member|all]"""
	if not Arguments:
		await Gears.Send(Bridge, "Error: invalid syntax.\n" + Help_usage)
		return
	Parts = Arguments.split()
	Action = Parts[0]

	if Action == "delegate":
		if len(Parts) < 2 or len(Parts) > 3:
			await Gears.Send(Bridge, "Error: invalid syntax.\n" + Help_usage)
			return
		Proxy_holder = Parts[1]
		Proxy_giver = None
		if len(Parts) == 3:
			# Consistency over intuition: the first argument is always Proxy_holder
			Proxy_giver = Parts[2]
		await Polls_proxy_delegate(Bridge, Context, User, Is_moderator, Proxy_holder, Proxy_giver)

	elif Action == "info":
		if len(Parts) != 2:
			await Gears.Send(Bridge, "Error: invalid syntax.\n" + Help_usage)
			return
		Member = Parts[1]
		if Member == "all":
			if len(Proxies) > 0:
				for Proxy_holder in Proxies:
					Output += f"{Proxy_holder} ← "
					Output += ", ".join(Proxy for Proxy in Proxies[Proxy_holder])
					Output += "\n"
			else:
				Output += f"No one has delegated a proxy."
		elif Member in Proxies:
			Output += f"{Member} hold the following proxies: "
			Output += ", ".join(Proxy for Proxy in Proxies[Member])
		else:
			Output += f"{Member} doesn’t hold any proxies."
		await Gears.Send(Bridge, Output)

	elif Action == "revoke":
		Member_revoking = None
		# Handle “!proxy revoke”
		if len(Parts) == 1:
			Member_revoking = User
		# Handle “!proxy revoke Member|all”
		if len(Parts) == 2:
			Member_revoking = Parts[1]
		Handler_to_revoke = None
		for Proxy_holder in Proxies:
			if Member_revoking in Proxies[Proxy_holder]:
				Handler_to_revoke = Proxy_holder
		if not Handler_to_revoke:
			await Gears.Send(Bridge, "{Member_revoking} didn’t delegate a proxy to anyone.")
			return
		Proceed_with_revocation = False
		if (Member_revoking == User or Handler_to_revoke == User):
			Proceed_with_revocation = True
		else:
			if not Is_moderator:
				await Gears.Send(Bridge,
						"Error: only moderators can revoke the proxy of someone else."
				)
				return
			if Member_revoking == "all":
				Proxies = {}
				Output += f"All proxies have been revoked."
			else:
				Proceed_with_revocation = True
		if Proceed_with_revocation:
			del Proxies[Handler_to_revoke][Member_revoking]
			if len(Proxies[Proxy_holder]) == 0:
				del Proxies[Proxy_holder]
			Output += f"{Member_revoking} no longer delegate a proxy to {Handler_to_revoke}."
		await Gears.Send(Bridge, Output)

	# Action isn’t delegate, info or revoke
	else:
		await Gears.Send(Bridge, "Error: invalid syntax.\n" + Help_usage)
		return

@polls.command(name="proxy")
async def Discord_polls_proxy(Context, *, Arguments):
	"""Manage votes by proxy.\n
	 \n
	!polls proxy delegate Holder [Member]\n
	!polls proxy info Member | all\n
	!polls proxy revoke [Member | all]
	Parameters
	----------
	Arguments : str"""

	Is_moderator = Context.author.guild_permissions.manage_messages
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_proxy(Bridge, Context.author.display_name, Is_moderator, Arguments, Context)

async def IRC_polls_proxy(Bridge, User, Arguments):
	Is_user_op = IRC_manager.Is_op(Bridge["irc_chan"], User)
	await Polls_proxy(Bridge, User, Is_user_op, Arguments)

async def Polls_list(Bridge, Arguments=None, Author=None):
	Status = None
	Number = None
	Output = ""
	Output_IRC = ""
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if Author:
			if Arguments:
				Output_IRC = f"<\x02{Author}\x02> !polls list {Arguments}\n"
			else:
				Output_IRC = f"<\x02{Author}\x02> !polls list\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Help_usage = "Usage: !polls list [Number] | !polls list [active/closed] [Number]"
	if Arguments:
		Parts = Arguments.split()
		if len(Parts) > 2:
			Output = "Error: invalid syntax.\n" + Help_usage
			if IRC_enabled:
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
			if IRC_enabled:
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
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	for Infos_poll in Polls:
		Status = "active" if Infos_poll["Active"] else "closed"
		Output += f"#{Infos_poll['ID']} ({Status}) {Infos_poll['Question']}\n"
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="list")
async def Discord_polls_list(Context, *, Arguments=None):
	"""Display a list of polls (10 max | no number given = last 3 polls).\n
	 \n
	!polls list [Number]\n
	!polls list [active/closed] [Number]
	Parameters
	----------
	Arguments : str"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_list(Bridge, Arguments, Context.author.display_name)

async def Polls_info(Bridge, Poll_ID=None, Author=None):

	Output = ""
	Output_IRC = ""
	if IRC_enabled:
		# If the command was sent on Discord, relay it on IRC
		if Author:
			if Poll_ID:
				Output_IRC = f"<\x02{Author}\x02> !polls info {Poll_ID}\n"
			else:
				Output_IRC = f"<\x02{Author}\x02> !polls info\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return

	if Poll_ID:
		try:
			Poll_ID = int(Poll_ID)
			# To avoid a DB query in the other case, when the lastest poll is automatically selected
			Infos_poll = None
		except (TypeError, ValueError):
			Output += "Error: invalid poll ID.\nUsage: !polls info [Poll_ID]"
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
	# Select latest poll if none specified
	else:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			Output += "Error: no polls in the DB."
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Bridge, Output, Output_IRC)
			return
		Poll_ID = Infos_poll["ID"]
	# Avoid a DB query, in case the lastest poll was automatically selected
	if not Infos_poll:
		Infos_poll = DB_manager.Polls_fetch(Polls_table, Poll_ID)
	if not Infos_poll:
		Output += f"Error: poll {Poll_ID} doesn’t exist."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return

	Creation_date = datetime.datetime.strftime(Infos_poll["Creation_date"], "%d/%m/%Y")
	Choices = Infos_poll["Choices"]
	# Blank votes will be displayed after the votes
	Choices[0] = "Blank"
	Status = "active" if Infos_poll["Active"] else "closed"
	Number_of_voters = 0
	Votes_for_each_choice = {}
	for Choice_ID in Choices:
		Votes_for_each_choice[Choice_ID] = []
	for Voter, Choice_ID in Infos_poll["Votes"].items():
		if Choice_ID in Votes_for_each_choice:
			Votes_for_each_choice[Choice_ID].append(Voter)
			Number_of_voters += 1
	Output += f"Poll {Poll_ID} ({Status}) created {Creation_date} by {Infos_poll['Author']} : "
	Output += f"{Infos_poll['Question']}\n"
	if Number_of_voters == 0:
		Output += f"No one has voted in this poll yet."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Bridge, Output, Output_IRC)
		return
	Choices_with_votes = []
	Choices_without_votes = []
	for Choice_ID, Choice_text in Choices.items():
		Choice_voters = Votes_for_each_choice[Choice_ID]
		Choice_count = len(Choice_voters)
		if Choice_count > 0:
			Choices_with_votes.append([Choice_count, {
					# Can’t be a division by zero since Number_of_voters > 0
					"Percentage": int((Choice_count / Number_of_voters) * 100),
					"ID": Choice_ID,
					"Text": Choice_text,
					"Voters": Choice_voters
			}])
		else:
			Choices_without_votes.append([Choice_ID, Choice_text])
	# Sort the list by the first element of each sublist (= Percentage)
	Choices_with_votes.sort(key=lambda Choice: Choice[0], reverse=True)

	Result = "tied"
	# After “if Number_of_voters == 0:” Choices_with_votes[0] is always valid
	First_choice_count = Choices_with_votes[0][0]
	# In case only one choice was voted
	if len(Choices_with_votes) > 1:
		Second_choice_count = Choices_with_votes[1][0]
	else:
		Second_choice_count = 0
	# No tie: only one choice voted, or the first choice has more votes than the second choice
	if len(Choices_with_votes) == 1 or First_choice_count > Second_choice_count:
		# The blanks account for the majority
		if Choices_with_votes[0][1]["ID"] == 0:
			Result = "blanks"
		else:
			Result = "decided"
	else:
		Choices_with_same_votes = 0
		for Choice_count, Choice in Choices_with_votes:
			# A not blank choice, with the same number of votes as the first choice
			if Choice["ID"] > 0 and Choice_count == First_choice_count:
				Choices_with_same_votes += 1
		# If a choice is tied, but only with the blanks → this choice won the vote
		if Choices_with_same_votes == 1:
			Result = "decided"
	if Result == "decided":
		Output += f"Result: {Choices_with_votes[0][1]['Text']} "
		Output += f"({Choices_with_votes[0][0]}/{Number_of_voters})"
	elif Result == "tied":
		Output += f"Result: tie"
	elif Result == "blanks":
		Output += "Result: Blanks are in the majority"
	if len(Choices_without_votes) > 0:
		Output += " § Choices without votes: ["
		Index = 0
		for Choice_ID, Choice_text in Choices_without_votes:
			Index += 1
			Output += f"#{Choice_ID} {Choice_text}"
			if Index < len(Choices_without_votes):
				Output += "] ["
			else:
				Output += "]"
	Output += "\n"
	for Choice_count, Choice in Choices_with_votes:
		Output += f"#{Choice['ID']} {Choice['Percentage']}% {Choice['Text']} ({Choice_count} = "
		Output += ", ".join(Choice["Voters"]) + ")\n"
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Bridge, Output, Output_IRC)

@polls.command(name="info")
async def Discord_polls_info(Context, Poll_ID=None):
	"""Display informations about a poll.\n
	 \n
	!polls info [Poll_ID]
	Parameters
	----------
	Poll_ID : int"""
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Context.channel.id)
	if Bridge:
		await Polls_info(Bridge, Poll_ID, Context.author.display_name)
