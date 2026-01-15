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

def History_update_filename(Table, Old_filename, New_filename):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Check if there is an entry whose attachments field contains the value of Old_filename
		Cursor.execute(f"""
				SELECT message_id, attachments FROM {Table}
				WHERE attachments LIKE %s""",
				('%\\"' + Old_filename.replace("—", "\\\\u2014") + '\\"%',)
		)
		Result = Cursor.fetchone()
		if not Result:
			print("[DB] Error: There’s already a file with that name in the folder, but it wasn’t registered in the DB for that message")
			return
		Message_id = Result[0]
		Filenames = json.loads(Result[1])
		Updated_filenames = []
		for Filename in Filenames:
			if Filename == Old_filename:
				Updated_filenames.append(New_filename)
			else:
				Updated_filenames.append(Filename)
		# Convert the list into a string to store it into the DB
		Updated_filenames = json.dumps(Updated_filenames)
		Cursor.execute(f"""
				UPDATE {Table} SET attachments = %s
				WHERE message_id = %s""",
				(Updated_filenames, Message_id)
		)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_addition(Table, Date, Server_id, Chan_id, Message_id, Replied_message_id, Discord_username, Content, Attachments):
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
			Attachments = json.dumps(Attachments)
			Cursor.execute(f"""
					INSERT INTO {Table} (
							date_creation,
							server_id, chan_id, message_id,
							reply_to,
							user_name, content, attachments)
							VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
					, (
							Date,
							Server_id, Chan_id, Message_id,
							Replied_message_id,
							Discord_username, Content, Attachments
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
					attachments,
					reactions,
					date_deletion
					FROM {Table} WHERE message_id = %s""",
					(Message_id,))
		Result = Cursor.fetchone()
		DB_entry = []
		if Result:
			DB_entry = list(Result)
			DB_entry[7] = json.loads(DB_entry[7]) if DB_entry[7] else []
		return DB_entry
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_edition(Table, Keep, Message_id, Date, New_content, Updated_filenames):
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
		if not Result:
			print(f"[DB] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")
			return
		if Keep:
			Old_content = Result[1]
			Edited_content = f"{Old_content}\n\n<|--- Edited {Date} ---|>\n\n{New_content}"
			if Updated_filenames:
				Updated_filenames = json.dumps(Updated_filenames)
				Cursor.execute(f"""
						UPDATE {Table} SET content = %s, attachments = %s, edited = TRUE
						WHERE message_id = %s""",
						(Edited_content, Updated_filenames, Message_id)
				)
			else:
				Cursor.execute(f"""
						UPDATE {Table} SET content = %s, edited = TRUE
						WHERE message_id = %s""",
						(Edited_content, Message_id)
				)
		else:
			Cursor.execute(f"""
					UPDATE {Table} SET content = %s
					WHERE message_id = %s""",
					(New_content, Message_id)
			)

		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_deletion(Table, Keep, Message_id, Date, Updated_filenames):
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
		if not Result:
			print(f"[DB] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
			return
		if Keep:
			if Updated_filenames:
				Updated_filenames = json.dumps(Updated_filenames)
				Cursor.execute(f"""
						UPDATE {Table} SET attachments = %s, date_deletion = %s
						WHERE message_id = %s""",
						(Updated_filenames, Date, Message_id)
				)
			else:
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
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()
