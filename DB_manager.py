# -*- coding: utf-8 -*-

import sys
# This actually uses the package mysqlclient, a fork of MySQLdb adding Python 3 support
import MySQLdb
import json

from Config_manager import Config

def Connect_DB():
	try:
		Connection = MySQLdb.connect(**Config["mysqlclient"])
		return Connection
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)

def History_addition(Table, Date, Server_id, Chan_id, Message_id, Replied_message_id, Discord_username, Content):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Check if the message is in the DB
		Cursor.execute(f"""
				SELECT message_id FROM {Table}
				WHERE message_id = %s""",
				(Message_id,)
		)
		Result = Cursor.fetchone()
		if not Result:
			Cursor.execute(f"""
					INSERT INTO {Table} (
							date_creation,
							server_id, chan_id, message_id,
							reply_to,
							user_name, content)
							VALUES (%s, %s, %s, %s, %s, %s, %s)"""
					, (
							Date,
							Server_id, Chan_id, Message_id,
							Replied_message_id,
							Discord_username, Content
					)
			)
		else:
			print("[DB] Warning: this message was already stored in the DB.")
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_fetch_message(Table, Message_id):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
					SELECT
					date_creation,
					server_id,
					chan_id,
					message_id,
					reply_to,
					user_name,
					content,
					reactions,
					date_deletion
					FROM {Table} WHERE message_id = %s""",
					(Message_id,))
		return Cursor.fetchone()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_edition(Table, Keep, Message_id, Date, New_content):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Check if the message is in the DB
		Cursor.execute(f"""
				SELECT user_name, content FROM {Table}
				WHERE message_id = %s""",
				(Message_id,)
		)
		Result = Cursor.fetchone()
		if Result:
			if Keep:
				Old_content = Result[1]
				Edited_content = f"{Old_content}\n\n<|--- Edited {Date} ---|>\n\n{New_content}"
				Request = f"""
						UPDATE {Table} SET content = %s, edited = TRUE
						WHERE message_id = %s"""
			else:
				Edited_content = New_content
				Request = f"""
						UPDATE {Table} SET content = %s
						WHERE message_id = %s"""
			Cursor.execute(Request, (Edited_content, Message_id))
		else:
			print(f"[DB] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_deletion(Table, Keep, Message_id, Date):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Check if the message is in the DB
		Cursor.execute(f"""
				SELECT user_name FROM {Table}
				WHERE message_id = %s""",
				(Message_id,)
		)
		Result = Cursor.fetchone()
		if Result:
			if Keep:
				Cursor.execute(f"""
						UPDATE {Table} SET date_deletion = %s
						WHERE message_id = %s""",
						(Date, Message_id)
				)
			else:
				Cursor.execute(f"""
						DELETE FROM {Table} WHERE message_id = %s""",
						(Message_id,)
				)
		else:
			print(f"[DB] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()
