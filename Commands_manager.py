# -*- coding: utf-8 -*-
# “Commands” is susceptible to be a keyword used elsewhere → this file is named Commands_manager.py

import asyncio
import inspect
import random
import re
import hashlib
import datetime
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta

from Config_manager import Config, L10n
import DB_manager
import Gears
from Discord_manager import bot

Request_shutdown = asyncio.Event()
IRC_enabled = Config["Enabled_sections"]["IRC"]
if IRC_enabled:
	import IRC_manager
Users_enabled = Config["Enabled_sections"]["Users"]
if Users_enabled:
	Users_table = Config["Users"]["DB_table"]
Polls_enabled = Config["Enabled_sections"]["Polls"]
if Polls_enabled:
	Polls_table = Config["Polls"]["DB_table"]
# Times stored in the DB are in UTC
UTC = datetime.timezone.utc
# Timezone used when interpreting user input or displaying dates
Timezone = ZoneInfo(Config["Server_timezone"])
Straws_bag = {}
Straws_bag["Common_key"] = {}
Straws_bag["Participants"] = []
Proxies = {}

###############################################################################
# Dispatch IRC commands
###############################################################################

async def IRC_dispatcher(Bridge, User, Text):

	# The IRC_* functions are used when it’s necessary to handle arguments specifically for IRC
	Infos_straws = {
	#				 		Fonction					Arguments?
	"Direct_call":			Straws_current_state,
	"Subcommands": {
			"help":			(Straws_help,				False),
			"join":			(IRC_straws_join,			True),
			"contribute":	(IRC_straws_contribute,		True),
			"participants":	(IRC_straws_participants,	True),
			"draw":			(Straws_draw,				False),
			"reset":		(Straws_reset,				False),
	}}

	Infos_polls = {
	#				 		Fonction					Arguments?
	"Direct_call":			IRC_polls,
	"Subcommands": {
			"help":			(Polls_help,				False),
			"members":		(Polls_members,				True),
			"add_adhesion":	(Polls_add_adhesion,		True),
			"create":		(Polls_create,				True),
			"close":		(IRC_polls_close,			True),
			"delete":		(IRC_polls_delete,			True),
			"vote":			(Polls_vote,				True),
			"unvote":		(Polls_unvote,				True),
			"info":			(Polls_info,				True),
			"list":			(Polls_list,				True),
			"proxy":		(IRC_polls_proxy,			True),
	}}

	Commands = {
	#					 Destination (funct or dict)	Arguments?
			"quit":		(IRC_quit,						False),
			"help":		(No_help_for_IRC,				False),
			"roll":		(IRC_roll,						True),
			"straws":	(Infos_straws,					True),
			"polls":	(Infos_polls,					True),
	}

	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	Parts = Text.split(maxsplit=1)
	Command = Parts[0].replace("!", "")
	Remainder = Parts[1] if len(Parts) > 1 else None
	if Command not in Commands:
		await Gears.Send(Bridge, Localized_replies["CM_Dispatch_invalid_command"])
		return
	Infos_command, With_args = Commands[Command]
	# Commands without subcommands
	if inspect.isfunction(Infos_command):
		Function = Infos_command
		Arguments = Remainder
	else:
		# Command that accepts subcommands, but was called without one this time
		if not Remainder:
			Function = Infos_command["Direct_call"]
			await Function(Bridge, User)
			return
		Infos_subcommands = Infos_command["Subcommands"]
		Parts = Remainder.split(maxsplit=1)
		Subcommand_called = Parts[0]
		Arguments = Parts[1] if len(Parts) > 1 else None
		if Subcommand_called not in Infos_subcommands:
			await Gears.Send(Bridge, Localized_replies["CM_Dispatch_invalid_subcommand"])
			return
		Function, With_args = Infos_subcommands[Subcommand_called]
	if With_args:
		await Function(Bridge, User, Arguments)
	else:
		await Function(Bridge, User)

###############################################################################
# Misc
###############################################################################

async def No_help_for_IRC(Targets, User):
	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	await Gears.Send(Targets, Localized_replies["CM_No_help_irc"])

###############################################################################
# !quit
###############################################################################

async def Quit_command(Media, User):
	if User == Config[Media]["Bot_owner"]:
		Request_shutdown.set()

@bot.command(name="quit")
async def Discord_quit(Context):
	# Owner’s username, not display name
	await Quit_command("Discord", Context.author.name)

async def IRC_quit(Targets, User):
	await Quit_command("IRC", User)

###############################################################################
# !roll
###############################################################################

async def Roll_Dice(Targets, User, Dice, From_Discord=False):
	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC. Otherwise, IRC users will see a
	# response from the bot, without seeing the command that prompted it.
	if IRC_enabled and From_Discord:
		Output_IRC = f"<\x02{User}\x02> !roll {Dice}\n"
	try:
		# Accept NDN as well as NdN
		Dice = Dice.lower()
		Number_rolls, Faces = map(int, Dice.split("d"))
		Error_found = False
		if Faces > 1000:
			Error_found = True
			Output = Localized_replies["CM_Roll_error_faces"]
		if Number_rolls > 10000:
			Error_found = True
			Output = Localized_replies["CM_Roll_error_rolls"]
		if Error_found:
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Targets, Output, Output_IRC)
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
			Summary = Localized_replies["CM_Roll_summary"].format(
					Min=Min, Average=Average, Max=Max, Total=Total
			)
			if Number_rolls <= 100:
				Output += "\n" + Summary
			else:
				Output = Summary
	except Exception as Error:
		print(f"[Commands] Roll_Dice(): {Error}")
		Output = Localized_replies["CM_Roll_help_usage"]
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@bot.command()
async def roll(Context, Dice):
	"""Roll Dice in NdN format.\n
	 \n
	!roll NdN
	Parameters
	----------
	Dice : str"""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Roll_Dice(Targets, User, Dice, True)

async def IRC_roll(Targets, User, Dice):
	if not Dice:
		Language = Gears.Determine_language(User)
		Localized_replies = L10n[Language]
		await Gears.Send(Targets, Localized_replies["CM_Roll_help_usage"])
		return
	await Roll_Dice(Targets, User, Dice)

###############################################################################
# !straws
###############################################################################

async def Straws_current_state(Targets, User, From_Discord=False):

	global Straws_bag
	Presence_participants = False
	Presence_straws = False
	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	Output = ""
	Output_IRC = ""
	Display_help = False
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		Output_IRC = f"<\x02{User}\x02> !straws\n"
	if len(Straws_bag["Participants"]) > 0:
		Presence_participants = True
		Output += Localized_replies["CM_Straws_state_display_participants"] + " "
		Output += ", ".join(Straws_bag["Participants"]) + ".\n\n"
	if len(Straws_bag["Common_key"]) > 0:
		Presence_straws = True
		Output += Localized_replies["CM_Straws_state_display_words"] + "\n"
		for User, Straw in Straws_bag["Common_key"].items():
			Output += f"[{User}] {Straw}\n"

	if Presence_participants:
		if not Presence_straws:
			Display_help = True
			Output += Localized_replies["CM_Straws_state_error_bag"] + " "
	else:
		Display_help = True
		if not Presence_straws:
			Output += Localized_replies["CM_Straws_state_error_participants_bag"] + "\n"
		else:
			Output += "\n" + Localized_replies["CM_Straws_state_error_participants"] + " "
	if Display_help:
		Output += Localized_replies["CM_Straws_help_usage"]
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@bot.group()
async def straws(Context):
	"""Draw straws among a group, with a reproducible pseudo-randomness."""
	Output_IRC = ""
	if Context.invoked_subcommand is None:
		Targets = Gears.Get_target_chans(Context.channel.id)
		User = Context.author.display_name
		# If there’s something after “!straws”, but it’s not a valid subcommand
		if Context.subcommand_passed is not None:
			Language = Gears.Determine_language(User)
			Localized_replies = L10n[Language]
			Output = Localized_replies["CM_Straws_invalid_subcommand"]
			if IRC_enabled:
				Output_IRC = f"<\x02{User}\x02> !straws {Context.subcommand_passed}\n" + Output
			await Gears.Send(Targets, Output, Output_IRC)
			return
		# If no subcommand is invoked, show what’s currently in the bag
		await Straws_current_state(Targets, User, True)

async def Straws_help(Targets, User, From_Discord=False):
	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		Output_IRC = f"<\x02{User}\x02> !straws help\n"
	Output = Localized_replies["CM_Straws_help_usage"]
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@straws.command(name="help")
async def Discord_straws_help(Context):
	"""Placeholder redirecting towards !help straws"""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Straws_help(Targets, User)

# This function requires Context as an argument, so it replaces From_Discord
async def Straws_add(Targets, User, Action, Straw, Context=None):
	global Straws_bag
	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	if IRC_enabled:
		IRC_instance = IRC_manager.GCI()
		# If the command was sent on Discord, relay it on IRC
		if Context:
			if IRC_instance:
				# No usage of Output_IRC for this function, because confirmations are sent privately
				await IRC_instance.Relay_Discord_message(
						Targets["IRC_chan"], User, f"!straws {Action} {Straw}"
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
		if Action == "join":
			if User not in Straws_bag["Participants"]:
				Straws_bag["Participants"].append(User)
			Straws_bag["Common_key"].update({User: Straw})
		if Action == "contribute":
			Straws_bag["Common_key"].update({User: Straw})
	except Exception as Error:
		print(f"[Commands] Straws_add(): {Error}")
		await Gears.Send(Targets, Localized_replies["CM_Straws_add_error"])
		return
	# Context will be None if the request comes from IRC, so the response will be correctly sent as
	# a query on IRC
	await Gears.Send_DM(User, Context,
			Localized_replies["CM_Straws_add_result"].format(Straw=Straw)
	)

@straws.command(name="join")
async def Discord_straws_join(Context, *, Word):
	"""Put a straw in the bag (and join in the draw).\n
	 \n
	!straws join Word
	Parameters
	----------
	Word : str"""
	# A straw is a word, or several that will be concatenated, in both cases up to 30 letters
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Straws_add(Targets, User, "join", Word, Context)

async def IRC_straws_join(Targets, User, Word):
	if not Word:
		Language = Gears.Determine_language(User)
		Localized_replies = L10n[Language]
		await Gears.Send(Targets, Localized_replies["CM_Straws_join_help_usage"])
		return
	await Straws_add(Targets, User, "join", Word)

@straws.command(name="contribute")
async def Discord_straws_contribute(Context, *, Word):
	"""Put a straw in the bag (without participating in the draw).\n
	 \n
	!straws contribute Word
	Parameters
	----------
	Word : str"""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Straws_add(Targets, User, "contribute", Word, Context)

async def IRC_straws_contribute(Targets, User, Word):
	if not Word:
		Language = Gears.Determine_language(User)
		Localized_replies = L10n[Language]
		await Gears.Send(Targets, Localized_replies["CM_Straws_contribute_help_usage"])
		return
	await Straws_add(Targets, User, "contribute", Word)

async def Straws_participants(Targets, User, Participants, From_Discord=False):
	global Straws_bag
	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		Output_IRC = f"<\x02{User}\x02> !straws participants {Participants}\n"
	if len(Participants) > 50:
		Output = Localized_replies["CM_Straws_participants_too_many"]
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return
	Straws_bag["Participants"] = []
	for Participant in Participants.split():
		Straws_bag["Participants"].append(Participant[:30])
	Output = Localized_replies["CM_Straws_participants_result"]
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@straws.command(name="participants")
async def Discord_straws_participants(Context, *, Participants):
	"""Set the list of participants for the draw.\n
	 \n
	!straws participants Participant1 [Participant2] […]
	Parameters
	----------
	Participants : str"""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	if Context.guild is None:
		Language = Gears.Determine_language(User)
		Localized_replies = L10n[Language]
		await Gears.Send_DM(None, Context, Localized_replies["CM_Command_not_private"])
		return
	await Straws_participants(Targets, User, Participants, True)

async def IRC_straws_participants(Targets, User, Participants):
	if not Participants:
		Language = Gears.Determine_language(User)
		Localized_replies = L10n[Language]
		await Gears.Send_DM(None, Context, Localized_replies["CM_Straws_participants_help_usage"])
		return
	await Straws_participants(Targets, User, Participants)

async def Straws_draw(Targets, User, From_Discord=False):

	global Straws_bag
	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		Output_IRC = f"<\x02{User}\x02> !straws draw\n"
	if len(Straws_bag["Participants"]) == 0:
		await Gears.Send(Targets, Localized_replies["CM_Straws_draw_error_participants"])
		return
	if len(Straws_bag["Common_key"]) == 0:
		await Gears.Send(Targets, Localized_replies["CM_Straws_draw_error_straws"])
		return

	Common_key = " ".join(Straws_bag["Common_key"].values())
	Hashes = {}
	for Participant in Straws_bag["Participants"]:
		# Create a dedicated key for each participant, by appending their name to the common key
		Participant_key = (Common_key + Participant).encode("utf8")
		# Calculate a hash for each participant’s key
		Hashes[Participant] = hashlib.sha512(Participant_key).hexdigest()
	# To avoid modifying the original list, create an sorted copy, from smallest to biggest hash
	Participants = sorted(Straws_bag["Participants"], key=lambda Participant: Hashes[Participant])

	Output += Localized_replies["CM_Straws_draw_display_participants"] + " "
	Output += ", ".join(Straws_bag["Participants"]) + ".\n\n"
	Output += Localized_replies["CM_Straws_draw_display_key"].format(Common_key=Common_key) + "\n"
	Output += Localized_replies["CM_Straws_draw_announce_hashes"] + "\n"
	for Participant in Straws_bag["Participants"]:
		# Display only the beginning of the hash: it’s more readable, and sufficient to verify
		Beginning_hash = Hashes[Participant][:30]
		Output += f"[{Participant}] {Beginning_hash}[…]\n"
	# Shortest straw = smallest hash 
	Lucky_one = Participants[0]
	Output += "\n" + Localized_replies["CM_Straws_draw_lucky_one"].format(Lucky_one=Lucky_one)
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@straws.command(name="draw")
async def Discord_straws_draw(Context):
	"""Pull a straw from the bag."""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	if Context.guild is None:
		Language = Gears.Determine_language(User)
		Localized_replies = L10n[Language]
		await Gears.Send_DM(None, Context, Localized_replies["CM_Command_not_private"])
		return
	await Straws_draw(Targets, User, True)

async def Straws_reset(Targets, User, From_Discord=False):
	global Straws_bag
	Language = Gears.Determine_language(User)
	Localized_replies = L10n[Language]
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		Output_IRC = f"<\x02{User}\x02> !straws reset\n"
	Straws_bag["Common_key"] = {}
	Straws_bag["Participants"] = []
	Output = Localized_replies["CM_Straws_reset"]
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@straws.command(name="reset")
async def Discord_straws_reset(Context):
	"""Reset the draw (delete participants and straws)."""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	if Context.guild is None:
		Language = Gears.Determine_language(User)
		Localized_replies = L10n[Language]
		await Gears.Send_DM(None, Context, Localized_replies["CM_Command_not_private"])
		return
	await Straws_reset(Targets, User, True)

###############################################################################
# !polls
###############################################################################

@bot.group()
async def polls(Context):
	"""Organize votes and participate in them."""
	Output_IRC = ""
	if Context.invoked_subcommand is None:
		Targets = Gears.Get_target_chans(Context.channel.id)
		User = Context.author.display_name
		# If there’s something after “!polls”, but it’s not a valid subcommand
		if Context.subcommand_passed is not None:
			Output = "Invalid subcommand. See !help polls"
			if IRC_enabled:
				Output_IRC = f"<\x02{User}\x02> !polls {Context.subcommand_passed}\n" + Output
			await Gears.Send(Targets, Output, Output_IRC)
			return
		# If no subcommand is invoked: “!polls” = “!polls list”
		# Arguments: Polls_list(Targets, User, Arguments=None, From_Discord=False):
		await Polls_list(Targets, User, None, True)

async def IRC_polls(Targets, User):
	await Polls_list(Targets, User)

async def Polls_help(Targets, User, From_Discord=False):
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		Output_IRC = f"<\x02{User}\x02> !polls help\n"
	Output = "See !help polls"
	await Gears.Send(Targets, Output, Output_IRC)

@polls.command(name="help")
async def Discord_polls_help(Context):
	"""Placeholder redirecting towards !help polls"""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Polls_help(Targets, User)

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
		# A datetime representing January 1st of the penultimate year, in UTC
		Infos_user["Penultimate_year"] = datetime.datetime(Penultimate_year, 1, 1, tzinfo=UTC)
	# Times stored in the DB are UTC
	Now = datetime.datetime.now(UTC)
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

async def Polls_members(Targets, User, List_of_users, From_Discord=False):

	Unregistered_users = []
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		if List_of_users:
			Output_IRC = f"<\x02{User}\x02> !polls members {List_of_users}\n"
		else:
			Output_IRC = f"<\x02{User}\x02> !polls members\n"
	if not Users_enabled:
		Output += "Error: This command requires the users section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return
	Users = DB_manager.Users_fetch_users(Users_table)

	# “!polls members” without arguments → list all members with voting rights
	if not List_of_users:
		List_of_users_from_argument = False
		Users_to_display = Users
	else:
		List_of_users_from_argument = True
		Users_to_display = {}
		# List_of_users is a string
		for Pseudo in List_of_users.split():
			User_ID = DB_manager.Users_check_presence(Users_table, {"Pseudo": Pseudo})
			if User_ID:
				Users_to_display[User_ID] = Users[User_ID]
			else:
				Unregistered_users.append(Pseudo)
	if len(Unregistered_users) > 0:
		if len(Unregistered_users) == 1:
			Output += f"{Unregistered_users[0]} isn’t a member.\n"
		else:
			for Unregistered_user in Unregistered_users:
				Output += f"{Unregistered_user} "
			Output += "aren’t members.\n"
		if not Users_to_display:
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Targets, Output, Output_IRC)
			return

	Number_voting_members = 0
	for User_ID in Users_to_display:
		Infos_user = Users_to_display[User_ID]
		Infos_user = Polls_voting_rights(Infos_user)
		# If we display all voting members, keep a concise display
		if not List_of_users_from_argument:
			if Infos_user["Can_vote"]:
				Number_voting_members += 1
				Output += f"{Infos_user['Pseudo']} "
			continue
		if Infos_user["Can_vote"]:
			Output += f"{Infos_user['Pseudo']} can vote "
		else:
			Output += f"{Infos_user['Pseudo']} can’t vote "
		Registration = Infos_user["Registration"].astimezone(Timezone).strftime("%d/%m/%Y")
		Last_renewal = Infos_user["Last_renewal"].astimezone(Timezone).strftime("%d/%m/%Y")
		if Infos_user["Penultimate_year"]:
			Penultimate_year = Infos_user["Penultimate_year"].strftime("%Y")
			Output += f"(Last renewal {Last_renewal} | Penultimate for {Penultimate_year})\n"
		else:
			Output += f"(last renewal {Last_renewal} | registration {Registration})\n"
	if not List_of_users_from_argument:
		if Number_voting_members > 0:
			Output = f"({Number_voting_members}) " + Output
		else:
			Output = "Nobody have voting rights."

	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@polls.command(name="members")
async def Discord_polls_members(Context, *, List_of_users=None):
	"""Display informations about members’ voting rights.\n
	 \n
	!polls members [Member1 Member2 …]
	Parameters
	----------
	List_of_users : str"""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Polls_members(Targets, User, List_of_users, True)

async def Polls_add_adhesion(Targets, User, Arguments, Context=None):

	Output = ""
	Output_IRC = ""
	if Context:
		Media = "Discord"
		# Owner’s username, not display name
		Command_author = Context.author.name
		if IRC_enabled:
			Output_IRC = f"<\x02{User}\x02> !polls add_adhesion {Arguments}\n"
	else:
		Media = "IRC"
		Command_author = User
	Help_usage = "Usage: !polls add_adhesion Pseudo Mail_address [YYYYMMDD]"
	if Command_author != Config[Media]["Bot_owner"]:
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		await Gears.Send_DM(User, Context, "Permission denied.")
		return
	if not Arguments:
		Output = Help_usage
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return
	Parts = Arguments.split()
	if len(Parts) < 2 or len(Parts) > 3:
		Output += "Error: invalid syntax. " + Help_usage
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return
	Pseudo = Parts[0]
	Mail = Parts[1]
	# [^@\s]+ → one or more characters that aren’t @ or space
	if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", Mail):
		Output = "Error: invalid mail address. " + Help_usage
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return
	if len(Parts) == 2:
		Date = datetime.datetime.now(Timezone)
	elif len(Parts) == 3:
		Date = Parts[2]
		try:
			# The given date is interpreted as being in Timezone
			Date = datetime.datetime.strptime(Date, "%Y%m%d").replace(tzinfo=Timezone)
		except ValueError:
			Output += "Error: invalid date. " + Help_usage
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Targets, Output, Output_IRC)
			return
	Year = Date.year
	# Times stored in the DB are UTC
	Date = Date.astimezone(UTC)
	Infos_user = {
			"Pseudo": Pseudo,
			"Mail": Mail
	}
	# To be placed here, because if it’s placed at the beginning of the function alongside the
	# initialization of other variables, it’ll cause a complete DB fetch even in case of syntax
	# errors or unauthorized calls
	Users = DB_manager.Users_fetch_users(Users_table)
	User_ID = DB_manager.Users_check_presence(Users_table, Infos_user)

	# Renewal
	if User_ID:
		Infos_user = Users[User_ID]
		Renewals = []
		for Renewal in Infos_user["Renewals"].values():
			Renewals.extend(Renewal)
		if Year in Infos_user["Renewals"] and Date in Infos_user["Renewals"][Year]:
			Date = Date.astimezone(Timezone).strftime("%d/%m/%Y")
			Output = f"Error: {Pseudo} already has a renewal for {Date}."
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Targets, Output, Output_IRC)
			return
		# max() doesn’t need Renewals.sort(), and this dictionary won’t be used for the DB
		Last_renewal = max(Renewals, default=None)
		# Some infos are updated only if it’s the latest renewal
		if not Last_renewal or Last_renewal < Date:
			Infos_user["Mail"] = Mail
			Infos_user["Last_medium"] = "Harmonia"
		# Make sure the key exists before appending the date
		if Year not in Infos_user["Renewals"]:
			Infos_user["Renewals"][Year] = []
		if Date not in Infos_user["Renewals"][Year]:
			Infos_user["Renewals"][Year].append(Date)
			Infos_user["Renewals"][Year].sort()
			Infos_user["Renewals"] = dict(sorted(Infos_user["Renewals"].items()))
		DB_manager.Users_manage_user(Users_table, "Update", Infos_user)
		Date = Date.astimezone(Timezone).strftime("%d/%m/%Y")
		Output = f"{Pseudo}’s membership has been renewed for {Date}."
	# New member
	else:
		# Complete the dictionary, in addition to what we got from the arguments
		Infos_user["First_name"] =					None
		Infos_user["Last_name"] =					None
		Infos_user["ML_pseudo"] =					None
		Infos_user["Wiki_pseudo"] =					None
		Infos_user["IRC_pseudo"] =					None
		Infos_user["Forum_pseudo"] =				None
		Infos_user["Discord_username"] =			None
		Infos_user["Pseudo_displayed_on_Discord"] = None
		Infos_user["Discord_expiration_for_IRC"] =	None
		Infos_user["History_keep_all"] =			True
		Infos_user["Avatar_URL"] =					None
		Infos_user["Renewals"] =					{Year: [Date]}
		Infos_user["Contributions"] =				None
		Infos_user["Last_medium"] =					"Harmonia"
		DB_manager.Users_manage_user(Users_table, "Add", Infos_user)
		Date = Date.astimezone(Timezone).strftime("%d/%m/%Y")
		Output = f"{Pseudo} has been added with membership date {Date}."

	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@polls.command(name="add_adhesion")
async def Discord_polls_add_adhesion(Context, *, Arguments):
	"""Record a membership renewal.\n
	 \n
	!polls add_adhesion Pseudo Mail_address [YYYYMMDD]
	Parameters
	----------
	Arguments : str"""
	if Context.guild is None:
		await Gears.Send_DM(None, Context, "Error: This command isn’t available in private.")
		return
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Polls_add_adhesion(Targets, User, Arguments, Context)

async def Polls_create(Targets, User, Arguments, From_Discord=False):
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		Output_IRC = f"<\x02{User}\x02> !polls create {Arguments}\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return
	if not Arguments:
		Output += "Usage: !polls create Subject [§ Choice 1 ; Choice 2 ; …]"
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
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
			await Gears.Send(Targets, Output, Output_IRC)
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
	await Gears.Send(Targets, Output, Output_IRC)

@polls.command(name="create")
async def Discord_polls_create(Context, *, Arguments):
	"""Create a new poll.\n
	 \n
	!polls create Subject [§ Choice 1 ; Choice 2 ; …]
	Parameters
	----------
	Arguments : str"""
	if Context.guild is None:
		await Gears.Send_DM(None, Context, "Error: This command isn’t available in private.")
		return
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Polls_create(Targets, User, Arguments, True)

async def Polls_close(Targets, User, Is_moderator, Arguments, From_Discord=False):

	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		if Arguments:
			Output_IRC = f"<\x02{User}\x02> !polls close {Arguments}\n"
		else:
			Output_IRC = f"<\x02{User}\x02> !polls close\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return

	# Select latest poll if none specified
	Polls_IDs = []
	if not Arguments:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			Output += "Error: no polls in the DB."
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Targets, Output, Output_IRC)
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
	await Gears.Send(Targets, Output, Output_IRC)

@polls.command(name="close")
async def Discord_polls_close(Context, *, Arguments=None):
	"""Close one or several poll (the latest if no ID is specified).\n
	 \n
	!polls close [Poll_ID] [Poll_ID] […]
	Parameters
	----------
	Arguments : int"""
	if Context.guild is None:
		await Gears.Send_DM(None, Context, "Error: This command isn’t available in private.")
		return
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	Is_moderator = Context.author.guild_permissions.manage_messages
	await Polls_close(Targets, User, Is_moderator, Arguments, True)

async def IRC_polls_close(Targets, User, Arguments=None):
	# If this function is called, IRC_manager will have been imported 
	Is_user_op = IRC_manager.Is_op(Targets["IRC_chan"], User)
	await Polls_close(Targets, User, Is_user_op, Arguments)

async def Polls_delete(Targets, User, Is_moderator, Arguments, From_Discord=False):

	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		if Arguments:
			Output_IRC = f"<\x02{User}\x02> !polls delete {Arguments}\n"
		else:
			Output_IRC = f"<\x02{User}\x02> !polls delete\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return

	# Select latest poll if none specified
	Polls_IDs = []
	if not Arguments:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			Output += "Error: no polls in the DB."
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Targets, Output, Output_IRC)
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
	await Gears.Send(Targets, Output, Output_IRC)

@polls.command(name="delete")
async def Discord_polls_delete(Context, *, Arguments=None):
	"""Delete one or several poll (the latest if no ID is specified).\n
	 \n
	!polls delete [Poll_ID] [Poll_ID] […]
	Parameters
	----------
	Arguments : int"""
	if Context.guild is None:
		await Gears.Send_DM(None, Context, "Error: This command isn’t available in private.")
		return
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	Is_moderator = Context.author.guild_permissions.manage_messages
	await Polls_delete(Targets, User, Is_moderator, Arguments, True)

async def IRC_polls_delete(Targets, User, Arguments=None):
	Is_user_op = IRC_manager.Is_op(Targets["IRC_chan"], User)
	await Polls_delete(Targets, User, Is_user_op, Arguments)

# This function requires Context as an argument, so it replaces From_Discord
async def Polls_vote(Targets, User, Arguments, Context=None):

	global Proxies
	if IRC_enabled:
		IRC_instance = IRC_manager.GCI()
		# If the command was sent on Discord, relay it on IRC
		if Context:
			if IRC_instance:
				# No usage of Output_IRC for this function, because user related errors are sent
				# privately
				await IRC_instance.Relay_Discord_message(Targets["IRC_chan"], User,
						f"<\x02{User}\x02> !polls vote {Arguments}"
				)
	if not Polls_enabled:
		await Gears.Send(Targets,
				"Error: This command requires the polls section to be enabled in the config file."
		)
		return
	if not Users_enabled:
		await Gears.Send(Targets,
				"Error: This command requires the users section to be enabled in the config file."
		)
		return
	Help_usage = "Usage: !polls vote <Choice_number> [Poll_ID]"
	if not Arguments:
		await Gears.Send(Targets, Help_usage)
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
			await Gears.Send(Targets,
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
			await Gears.Send(Targets, f"Error: invalid poll ID or choice number.\n" + Help_usage)
			return
	# Select latest poll if none specified
	elif len(Parts) == 1:
		try:
			Choice = int(Parts[0])
		except ValueError:
			await Gears.Send(Targets, f"Error: invalid choice number.\n" + Help_usage)
			return
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			await Gears.Send(Targets, "Error: no polls in the DB.")
			return
		Poll_ID = Infos_poll["ID"]
	else:
		await Gears.Send(Targets, Help_usage)
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
		await Gears.Send(Targets, "Error: poll not found. See !polls list")
		return
	if not Infos_poll["Active"]:
		await Gears.Send(Targets, f"Error: poll {Poll_ID} is closed. See !polls list active")
		return
	Choices = Infos_poll["Choices"]
	if Choice < 0 or Choice > len(Choices):
		await Gears.Send(Targets, f"Error: invalid choice number. See !polls info {Poll_ID}")
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
	if Context.guild is None:
		await Gears.Send_DM(None, Context, "Error: This command isn’t available in private.")
		return
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Polls_vote(Targets, User, Arguments, Context)

# This function requires Context as an argument, so it replaces From_Discord
async def Polls_unvote(Targets, User, Poll_ID=None, Context=None):
	if IRC_enabled:
		IRC_instance = IRC_manager.GCI()
		# If the command was sent on Discord, relay it on IRC
		if Context:
			if IRC_instance:
				if Poll_ID:
					Output = f"<\x02{User}\x02> !polls unvote {Poll_ID}\n"
				else:
					Output = f"<\x02{User}\x02> !polls unvote\n"
				# No usage of Output_IRC for this function, because user related errors are sent
				# privately
				await IRC_instance.Relay_Discord_message(Targets["IRC_chan"], User, Output)
	if not Polls_enabled:
		await Gears.Send(Targets,
				"Error: This command requires the polls section to be enabled in the config file."
		)
		return
	if Poll_ID:
		try:
			Poll_ID = int(Poll_ID)
			# To avoid a DB query in the other case, when the lastest poll is automatically selected
			Infos_poll = None
		except (TypeError, ValueError):
			await Gears.Send(Targets, "Error: invalid poll ID.\nUsage: !polls unvote [Poll_ID]")
			return
	# Select latest poll if none specified
	else:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			await Gears.Send(Targets, "Error: no polls in the DB.")
			return
		Poll_ID = Infos_poll["ID"]
	# Avoid a DB query, in case the lastest poll was automatically selected
	if not Infos_poll:
		Infos_poll = DB_manager.Polls_fetch(Polls_table, Poll_ID)
	if not Infos_poll:
		await Gears.Send(Targets, "Error: poll not found. See !polls list")
		return
	Votes = Infos_poll["Votes"]
	if User not in Votes:
		await Gears.Send_DM(User, Context, "Error: you didn’t vote in this poll.")
		return
	del Votes[User]
	Recorded_in_DB = False
	Recorded_in_DB = DB_manager.Polls_unvote(Polls_table, Poll_ID, Votes)
	if Recorded_in_DB:
		await Gears.Send(Targets, f"{User}’s vote has been removed from poll {Poll_ID}.")

@polls.command(name="unvote")
async def Discord_polls_unvote(Context, Poll_ID):
	"""When a member wants to withdraw their participation in a poll.\n
	 \n
	!polls unvote [Poll_ID]
	Parameters
	----------
	Poll_ID : str"""
	if Context.guild is None:
		await Gears.Send_DM(None, Context, "Error: This command isn’t available in private.")
		return
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Polls_unvote(Targets, User, Poll_ID, Context)

async def Polls_proxy_delegate(Targets, Context, User, Is_moderator, Proxy_holder, Proxy_giver):

	global Proxies
	Change_of_holder = False
	# No self-proxy (“not Proxy_giver” in case User is a moderator)
	if User == Proxy_holder and not Proxy_giver:
		await Gears.Send_DM(User, Context, "Error: a member cannot delegate to themselves.")
		return
	if not Users_enabled:
		await Gears.Send(Targets,
				"Error: This command requires the users section to be enabled in the config file."
		)
		return

	# Only members with voting rights can delegate a proxy
	User_ID = DB_manager.Users_check_presence(Users_table, {"Pseudo": User})
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
			await Gears.Send(Targets,
					"Error: only moderators can delegate the proxy of someone else."
			)
			return
	Now = datetime.datetime.now(Timezone)
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
		await Gears.Send(Targets, f"{Proxy_holder} already holds 3 proxies.")
		return
	Proxies[Proxy_holder][User] = Now
	Output = f"{User} delegated their proxy to {Proxy_holder}"
	if Change_of_holder:
		Output += f" (previously to {Old_holder})"

	# Simplest case: User doesn’t hold proxy to subdelegate, and Proxy_holder held up to 2 proxies.
	# Therefore by adding the proxy of User, Proxy_holder don’t exceed the limit of 3
	if not User in Proxies:
		Output += "."
		await Gears.Send(Targets, Output)
		return
	# When User holds proxies, but Proxy_holder can’t receive any of them
	if len(Proxies[Proxy_holder]) == 3:
		Output += f" (who now hold 3 proxies), however {User} held proxies that can’t be subdelegated ("
		Output += ", ".join(Proxy for Proxy in Proxies[User])
		Output += f")."
		del Proxies[User]
		await Gears.Send(Targets, Output)
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
	await Gears.Send(Targets, Output)

# This function requires Context as an argument, so it replaces From_Discord
async def Polls_proxy(Targets, User, Is_moderator, Arguments, Context=None):

	global Proxies
	Output = ""
	if IRC_enabled:
		IRC_instance = IRC_manager.GCI()
		# If the command was sent on Discord, relay it on IRC
		if Context:
			if IRC_instance:
				# No usage of Output_IRC for this function, because user related errors are sent
				# privately
				await IRC_instance.Relay_Discord_message(
						Targets["IRC_chan"], User, f"!polls proxy {Arguments}"
				)
	Help_usage = "Usage: !polls proxy delegate Proxy_holder [Member] | !polls proxy info Member|all | !polls proxy revoke [Member|all]"""
	if not Arguments:
		await Gears.Send(Targets, "Error: invalid syntax.\n" + Help_usage)
		return
	Parts = Arguments.split()
	Action = Parts[0]

	if Action == "delegate":
		if len(Parts) < 2 or len(Parts) > 3:
			await Gears.Send(Targets, "Error: invalid syntax.\n" + Help_usage)
			return
		Proxy_holder = Parts[1]
		Proxy_giver = None
		if len(Parts) == 3:
			# Consistency over intuition: the first argument is always Proxy_holder
			Proxy_giver = Parts[2]
		await Polls_proxy_delegate(Targets, Context, User, Is_moderator, Proxy_holder, Proxy_giver)

	elif Action == "info":
		if len(Parts) != 2:
			await Gears.Send(Targets, "Error: invalid syntax.\n" + Help_usage)
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
		await Gears.Send(Targets, Output)

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
			await Gears.Send(Targets, "{Member_revoking} didn’t delegate a proxy to anyone.")
			return
		Proceed_with_revocation = False
		if (Member_revoking == User or Handler_to_revoke == User):
			Proceed_with_revocation = True
		else:
			if not Is_moderator:
				await Gears.Send(Targets,
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
		await Gears.Send(Targets, Output)

	# Action isn’t delegate, info or revoke
	else:
		await Gears.Send(Targets, "Error: invalid syntax.\n" + Help_usage)
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
	if Context.guild is None:
		await Gears.Send_DM(None, Context, "Error: This command isn’t available in private.")
		return
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	Is_moderator = Context.author.guild_permissions.manage_messages
	await Polls_proxy(Targets, User, Is_moderator, Arguments, Context)

async def IRC_polls_proxy(Targets, User, Arguments):
	Is_user_op = IRC_manager.Is_op(Targets["IRC_chan"], User)
	await Polls_proxy(Targets, User, Is_user_op, Arguments)

async def Polls_list(Targets, User, Arguments=None, From_Discord=False):
	Status = None
	Number = None
	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		if Arguments:
			Output_IRC = f"<\x02{User}\x02> !polls list {Arguments}\n"
		else:
			Output_IRC = f"<\x02{User}\x02> !polls list\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return
	Help_usage = "Usage: !polls list [Number] | !polls list [active/closed] [Number]"
	if Arguments:
		Parts = Arguments.split()
		if len(Parts) > 2:
			Output = "Error: invalid syntax.\n" + Help_usage
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Targets, Help_usage, Output_IRC)
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
			await Gears.Send(Targets, Output, Output_IRC)
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
		await Gears.Send(Targets, Output, Output_IRC)
		return
	for Infos_poll in Polls:
		Status = "active" if Infos_poll["Active"] else "closed"
		Output += f"#{Infos_poll['ID']} ({Status}) {Infos_poll['Question']}\n"
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@polls.command(name="list")
async def Discord_polls_list(Context, *, Arguments=None):
	"""Display a list of polls (10 max | no number given = last 3 polls).\n
	 \n
	!polls list [Number]\n
	!polls list [active/closed] [Number]
	Parameters
	----------
	Arguments : str"""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Polls_list(Targets, User, Arguments, True)

async def Polls_info(Targets, User, Poll_ID=None, From_Discord=False):

	Output = ""
	Output_IRC = ""
	# If the command was sent on Discord, relay it on IRC
	if IRC_enabled and From_Discord:
		if Poll_ID:
			Output_IRC = f"<\x02{User}\x02> !polls info {Poll_ID}\n"
		else:
			Output_IRC = f"<\x02{User}\x02> !polls info\n"
	if not Polls_enabled:
		Output = "Error: This command requires the polls section to be enabled in the config file."
		Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
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
			await Gears.Send(Targets, Output, Output_IRC)
			return
	# Select latest poll if none specified
	else:
		Infos_poll = DB_manager.Polls_fetch_list(Polls_table, 1, "latest")[0]
		if not Infos_poll:
			Output += "Error: no polls in the DB."
			if IRC_enabled:
				Output_IRC += Output
			await Gears.Send(Targets, Output, Output_IRC)
			return
		Poll_ID = Infos_poll["ID"]
	# Avoid a DB query, in case the lastest poll was automatically selected
	if not Infos_poll:
		Infos_poll = DB_manager.Polls_fetch(Polls_table, Poll_ID)
	if not Infos_poll:
		Output += f"Error: poll {Poll_ID} doesn’t exist."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
		return

	Creation_date = Infos_poll["Creation_date"].astimezone(Timezone).strftime("%d/%m/%Y")
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
		if Status == "active":
			Output += "Possible choices: "
			Choices_sorted = sorted(Choices.items())
			Output += " ".join(
					f"[#{Choice_ID} {Choice_text}]"
					for Choice_ID, Choice_text in Choices_sorted
			)
			Output += "\nNo one has voted in this poll yet."
		else:
			Output += "No one has voted in this poll."
		if IRC_enabled:
			Output_IRC += Output
		await Gears.Send(Targets, Output, Output_IRC)
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
	# Sort the list by percentage (first element of each sublist)
	Choices_with_votes.sort(key=lambda Choice: Choice[0], reverse=True)
	# Sort the list from smallest to greatest index number
	Choices_without_votes.sort(key=lambda Choice: Choice[0])

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
		Output += " § Choices without votes: "
		Output += " ".join(
				f"[#{Choice_ID} {Choice_text}]"
				for Choice_ID, Choice_text in Choices_without_votes
		)
	Output += "\n"
	for Choice_count, Choice in Choices_with_votes:
		Output += f"#{Choice['ID']} {Choice['Percentage']}% {Choice['Text']} ({Choice_count} = "
		Output += ", ".join(Choice["Voters"]) + ")\n"
	if IRC_enabled:
		Output_IRC += Output
	await Gears.Send(Targets, Output, Output_IRC)

@polls.command(name="info")
async def Discord_polls_info(Context, Poll_ID=None):
	"""Display informations about a poll.\n
	 \n
	!polls info [Poll_ID]
	Parameters
	----------
	Poll_ID : int"""
	Targets = Gears.Get_target_chans(Context.channel.id)
	User = Context.author.display_name
	await Polls_info(Targets, User, Poll_ID, True)
