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
Users_enabled = Config["Enabled_sections"]["Users"]

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
	if not Discord_manager.Reconcile_downloaded_files.is_running():
		if History_enabled:
			Discord_manager.Reconcile_downloaded_files.start()

###############################################################################
# Shutdown
###############################################################################

async def Stop_bot():
	print("Shutdown initiated…")
	if Shutdown_in_progress.is_set():
		return
	Shutdown_in_progress.set()
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
	# Stop Discord
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
