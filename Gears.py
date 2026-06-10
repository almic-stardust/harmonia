# -*- coding: utf-8 -*-

import asyncio

import Discord_manager
import IRC_manager

async def Wait_for_events(*Events):
	Tasks = [asyncio.create_task(Event) for Event in Events]
	Done, Pending = await asyncio.wait(Tasks, return_when=asyncio.FIRST_COMPLETED)
	for Task in Pending:
		Task.cancel()
	await asyncio.gather(*Pending, return_exceptions=True)
	return Done

async def Get_chans(Bridge):
	from Discord_manager import bot
	Discord_chan = bot.get_channel(Bridge["discord_chan"])
	if not Discord_chan:
		Discord_chan = await bot.fetch_channel(Bridge["discord_chan"])
	return Discord_chan, Bridge["irc_chan"]

async def Send(Bridge, Message, Message_IRC=None):
	"""Send a message both on Discord and IRC"""
	Discord_chan, IRC_chan = await Get_chans(Bridge)
	for Fragment in Discord_manager.Split_message(Message):
		await Discord_chan.send(Fragment)
	if IRC_chan:
		IRC_instance = IRC_manager.GCI()
		if IRC_instance:
			# If the message to be sent on IRC is different from the message for Discord
			if Message_IRC:
				await IRC_instance.Safe_message(IRC_chan, Message_IRC)
			else:
				await IRC_instance.Safe_message(IRC_chan, Message)

async def Send_DM(User, Context, Message, Message_IRC=None):
	"""Send a DM, either on Discord or IRC"""
	# The user wrote to the bot via Discord, reply via DM
	if Context:
		for Fragment in Discord_manager.Split_message(Message):
			await Discord_chan.send(Fragment)
	# The user wrote to the bot via IRC, reply via query
	else:
		IRC_instance = IRC_manager.GCI()
		if IRC_instance:
			# If the message to be sent via query is different from the DM on Discord
			if Message_IRC:
				await IRC_instance.Safe_message(User, Message_IRC)
			else:
				await IRC_instance.Safe_message(User, Message)
