# -*- coding: utf-8 -*-

import asyncio

from Config_manager import Config
import Discord_manager

Shutdown_in_progress = asyncio.Event()
IRC_enabled = Config["Enabled_sections"]["IRC"]
if IRC_enabled:
	import IRC_manager
	IRC_task = None
History_enabled = Config["Enabled_sections"]["History"]
if History_enabled:
	History_table = Config["History"]["DB_table"]
Users_enabled = Config["Enabled_sections"]["Users"]
if Users_enabled:
	Users_table = Config["Users"]["DB_table"]

###############################################################################
# Startup
###############################################################################

async def Start_bot():
	# Ensure async errors are visible (by default, discord.py silently drop task errors)
	Loop = asyncio.get_running_loop()
	Loop.set_exception_handler(lambda loop, context: print("ASYNC ERROR:", context))
	if len(Discord_manager.bot.guilds) == 0:
		print("[Discord] Bot is not yet in any server.")
		await Stop_bot()
		return
	print(f"[Discord] Logged in as {Discord_manager.bot.user}")
	if IRC_enabled:
		global IRC_task
		# Start IRC loop only once
		if IRC_task is None or IRC_task.done():
			IRC_task = asyncio.create_task(IRC_manager.Run_IRC_loop())
	# Start background tasks
	if IRC_enabled:
		if not Discord_manager.Delete_expired_IRC_messages_from_Discord.is_running():
			if History_enabled and Users_enabled:
				Discord_manager.Delete_expired_IRC_messages_from_Discord.start()
	if History_enabled:
		if not Discord_manager.Reconcile_downloaded_files.is_running():
			Discord_manager.Reconcile_downloaded_files.start()
		if Config["History"]["Sync_old"]:
			# Don’t add non-essential circular dependencies to this module
			from History import Synchronization
			if not Synchronization.is_running():
				Synchronization.start(History_table)

###############################################################################
# Shutdown
###############################################################################

async def Stop_bot():

	if Shutdown_in_progress.is_set():
		return
	print("Shutdown initiated…")
	Shutdown_in_progress.set()

	# Stop background tasks
	if History_enabled:
		if Discord_manager.Reconcile_downloaded_files.is_running():
			Discord_manager.Reconcile_downloaded_files.cancel()
			try:
				await Discord_manager.Reconcile_downloaded_files.get_task()
			except asyncio.CancelledError:
				pass
			except Exception as Error:
				print(f"Error while stopping Reconcile_downloaded_files(): {Error}")
		if Config["History"]["Sync_old"]:
			# Don’t add non-essential circular dependencies to this module
			from History import Synchronization
			if Synchronization.is_running():
				Synchronization.cancel()
				try:
					await Synchronization.get_task()
				except asyncio.CancelledError:
					pass
				except Exception as Error:
					print(f"Error while stopping history synchronization: {Error}")
	if IRC_enabled:
		if Discord_manager.Delete_expired_IRC_messages_from_Discord.is_running():
			Discord_manager.Delete_expired_IRC_messages_from_Discord.cancel()
			try:
				await Discord_manager.Delete_expired_IRC_messages_from_Discord.get_task()
			except asyncio.CancelledError:
				pass
			except Exception as Error:
				print(f"Error while stopping Delete_expired_IRC_messages_from_Discord(): {Error}")

	# Stop IRC loop
	if IRC_enabled:
		global IRC_task
		# Disconnect from IRC
		IRC_instance = IRC_manager.Get_instance()
		if IRC_instance:
			try:
				await IRC_instance.Shutdown_IRC()
			except Exception as Error:
				print(f"[IRC] Error during shutdown: {Error}")
		# Wait for the IRC loop to exit cleanly
		if IRC_task:
			try:
				await IRC_task
			except Exception as Error:
				print(f"[IRC] Error during task loop exit: {Error}")

	# Finally, disconnect from Discord
	await Discord_manager.Shutdown_Discord()
	print("Shutdown complete.")

###############################################################################
# Events
###############################################################################

async def Wait_for_events(*Events):
	Tasks = []
	for Event in Events:
		if isinstance(Event, asyncio.Task):
			Tasks.append(Event)
		else:
			Tasks.append(asyncio.create_task(Event))
	First_done, Pending_tasks = await asyncio.wait(Tasks, return_when=asyncio.FIRST_COMPLETED)
	return First_done, Pending_tasks

###############################################################################
# Users
###############################################################################

def Get_Discord_pseudo(User):
	# The bot is replying to someone, or saying something on its own
	if User == Discord_manager.bot.user:
		return Config["Discord"].get("Bot_name", "Bot")
	# User.display_name = the server nickname if set, otherwise the global display name if set,
	# otherwise the Discord username
	Author_name = User.display_name
	# If a user has requested that the bot assign them a specific name on Discord, then this name
	# will be used by Discord_manager.bot.Relay_IRC_message(). But for the history and messages
	# transferred to IRC, it’s the IRC nick that needs to be returned.
	if Users_enabled:
		# Don’t add non-essential circular dependencies to this module
		from DB_manager import Users_fetch_users
		Users = Users_fetch_users(Users_table)
		for User_ID in Users:
			Infos_user = Users[User_ID]
			if Infos_user["Pseudo_displayed_on_Discord"] == Author_name:
				Author_name = Infos_user.get("IRC_pseudo", Author_name)
				break
	return Author_name

###############################################################################
# Chans
###############################################################################

def Get_target_chans(Discord_chan):
	Targets = {}
	Targets["Discord_chan"] = Discord_chan
	Bridge = Discord_manager.Get_bridge_by_Discord_chan(Discord_chan)
	if Bridge:
		Targets["IRC_chan"] = Bridge["IRC_chan"]
	return Targets

###############################################################################
# Messages
###############################################################################

async def Send(Targets, Message, Message_IRC=None):
	"""Send a message both on Discord and IRC (if enabled)"""

	if not Targets["Discord_chan"]:
		print(f"[Gears] Error for Send(): no Discord chan to send to.")
	Discord_chan = Discord_manager.bot.get_channel(Targets["Discord_chan"])
	if not Discord_chan:
		Discord_chan = await Discord_manager.bot.fetch_channel(Targets["Discord_chan"])
	for Fragment in Discord_manager.Split_message(Message):
		await Discord_chan.send(Fragment)

	if IRC_enabled and Targets["IRC_chan"]:
		IRC_instance = IRC_manager.GCI()
		if IRC_instance:
			# If the message to be sent on IRC is different from the message for Discord
			if Message_IRC:
				await IRC_instance.Safe_message(Targets["IRC_chan"], Message_IRC)
			else:
				await IRC_instance.Safe_message(Targets["IRC_chan"], Message)

async def Send_DM(User, Context, Message, Message_IRC=None):
	"""Send a DM, either on Discord or IRC"""
	# The user wrote to the bot via Discord, reply via DM
	if Context:
		for Fragment in Discord_manager.Split_message(Message):
			await Context.author.send(Fragment)
	# The user wrote to the bot via IRC, reply via query
	else:
		IRC_instance = IRC_manager.GCI()
		if IRC_instance:
			# If the message to be sent via query is different from the DM on Discord
			if Message_IRC:
				await IRC_instance.Safe_message(User, Message_IRC)
			else:
				await IRC_instance.Safe_message(User, Message)

###############################################################################
# Files
###############################################################################

def Is_URL(Location):
	return Location.startswith(("http://", "https://"))
