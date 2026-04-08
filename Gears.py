# -*- coding: utf-8 -*-

import asyncio

async def Wait_for_events(*Events):
	Tasks = [asyncio.create_task(Event) for Event in Events]
	Done, Pending = await asyncio.wait(Tasks, return_when=asyncio.FIRST_COMPLETED)
	for Task in Pending:
		Task.cancel()
	await asyncio.gather(*Pending, return_exceptions=True)
	return Done
