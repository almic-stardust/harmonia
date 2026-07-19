# Harmonia

A Discord bot that saves history, display it on a website, and provides a bridge towards IRC.

# Code structure

The different sections of the bot are separated into modules.

Harmonia.py  
The script used to start the bot.

Config\_manager.py  
Loads and processes the configuration and localizations.

DB\_manager.py  
Manages database-related operations.

Discord\_related.py  
Functions specific to Discord, like handling events concerning sent/deleted messages (on\_message/on\_raw\_message\_delete).

IRC\_related.py  
Functions specific to IRC, using pydle.

display\_history/  
Everything related to the web display of the history.

# Installation

I’m using the bot on Debian 13 (trixie).

#### Python virtual environment

The python3-pydle package in trixie isn’t usable, we need to create a venv with pip.

Sentence from the output of the pip command:  
“If you wish to install a non-Debian-packaged Python package, create a virtual environment. […] Make
sure you have python3-full installed.”

	# apt install python3-full

To build the package mysqlclient:

	# apt install python3-dev default-libmysqlclient-dev build-essential pkg-config

Create the virtual environment:

	% python3.13 -m venv ~/.local/pydle-python3.13
	% ~/.local/pydle-python3.13/bin/python -m pip install discord.py pydle PyYAML mysqlclient python-dateutil

When you’ll have to upgrade the venv:

	% ~/.local/pydle-python3.13/bin/python -m pip install --upgrade pip
	% ~/.local/pydle-python3.13/bin/python -m pip install --upgrade --log ~/pip_log-`date +%Y%m%d` discord.py pydle PyYAML mysqlclient python-dateutil

When you’ll upgrade your Linux distribution, the Python version will change and you’ll have to recreate the venv.

#### Database

Create a base according to your Config.yaml, then create these tables. The creation\_date field of
the project\_history table prevents the SQL requests of some functions from requiring a JSON
extraction.

	CREATE TABLE project_history (
	    creation_date               TIMESTAMP NOT NULL,
	    server_id                   BIGINT NOT NULL,
	    chan_id                     BIGINT NOT NULL,
	    message_id                  BIGINT NOT NULL PRIMARY KEY,
	    reply_to                    BIGINT NULL,
	    user                        VARCHAR(32) NOT NULL,
	    content_history             TEXT NOT NULL,
	    attachments                 JSON NULL,
	    reactions                   JSON NULL,
	    relayed                     BOOLEAN NOT NULL DEFAULT FALSE,
	    expired                     BOOLEAN NOT NULL DEFAULT FALSE,
	    deletion_date               TIMESTAMP NULL
	);

	CREATE TABLE project_users (
	    pseudo                      VARCHAR(255) NULL,
	    id                          INT AUTO_INCREMENT PRIMARY KEY,
	    mail                        VARCHAR(255) NOT NULL,
	    first_name                  VARCHAR(255) NULL,
	    last_name                   VARCHAR(255) NULL,
	    ml_pseudo                   VARCHAR(255) NULL,
	    wiki_pseudo                 VARCHAR(255) NULL,
	    irc_pseudo                  VARCHAR(255) NULL,
	    forum_pseudo                VARCHAR(255) NULL,
	    discord_username            VARCHAR(255) NULL,
	    pseudo_displayed_on_discord VARCHAR(255) NULL,
	    discord_expiration_for_irc  INT NOT NULL,
	    history_keep_all            BOOLEAN NULL,
	    avatar_url                  VARCHAR(1024) NULL,
	    renewals                    JSON NULL,
	    contributions               JSON NULL,
	    last_medium                 VARCHAR(255) NULL
	);

	CREATE TABLE project_polls (
	    id                          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
	    creation_date               TIMESTAMP NOT NULL DEFAULT current_timestamp(),
	    user                        VARCHAR(255) NOT NULL,
	    question                    TEXT NOT NULL,
	    choices                     JSON NOT NULL,
	    votes                       JSON NULL,
	    proxies                     JSON NULL,
	    active                      BOOLEAN NOT NULL DEFAULT TRUE
	);

	CREATE TABLE history_sync (
	    server_id                   BIGINT NOT NULL,
	    chan_id                     BIGINT NOT NULL,
	    oldest_message_id           BIGINT NOT NULL,
	    latest_message_id           BIGINT NOT NULL,
	    PRIMARY KEY                 (server_id, chan_id, latest_message)
	);

For performance, create composite indexes in the DB:

	CREATE INDEX Index_latest_messages ON history_sync (server_id, chan_id, latest_message_id);


#### Last steps

	% git https://github.com/almic-stardust/harmonia
	% cd harmonia

Adjust the configuration to your needs:

Config\_dist.yaml  
Example of configuration file to modify. Rename it as Config.yaml

Finally, you can start the bot:

	% ~/.local/pydle-python3.13/bin/python3 Harmonia.py

# Web display of the history

Here is the procedure to set up this feature.

	% cd harmonia/display_history
	% for File in Config_manager.py Config.yaml DB_manager.py ; ln -s ../$File

For performance, create composite indexes in the DB:

	CREATE INDEX Index_messages ON project_history (server_id, chan_id, creation_date);
	CREATE INDEX Index_replies ON project_history (reply_to);
	CREATE INDEX Index_deletions ON project_history (server_id, chan_id, deletion_date);
	CREATE INDEX Index_expiration ON project_history (relayed, expired, creation_date);

The ASGI server I use is Hypercorn. On the system where you want to run it:

	# apt install python3-hypercorn python3-fastapi python3-yaml python3-mysqldb
	% cd harmonia/display_history
	% hypercorn -k uvloop -w 4 --bind localhost:60444 --certfile /path/to/cert.pem --keyfile /path/to/key.pem --access-logfile - Main:Display_history

Then you need to configure nginx (for example), with a site acting as a reverse proxy towards
localhost:60444. You also need a nginx alias /static/ for harmonia/display\_history/static/ and
another nginx alias /attachments/ for the storage folder specified in Config.yaml. Once this is
done, the history should be accessible at:

	https://domain.tld/chan/server_id/chan_id

It could be useful to create a SystemD unit, so that Hypercorn starts when the system boots. If you
read French, I wrote a [tutorial for Hypercorn](https://almic.fr/blog/2026/01/19/asgi-hypercorn/)
(nginx configuration, TLS certificate, and SystemD service).

Instead of Hypercorn you can use Uvicorn, which displays a digest log on its standard output. It’s
useful during development.

	# apt install uvicorn
	% python3 -m uvicorn Main:Display_history --host LAN_IP --port 60081 --reload

Or, if you must have the very latest version:

	% python3 -m venv ~/.local/uvicorn-python3.13
	% ~/.local/uvicorn-python3.13/bin/pip install uvicorn fastapi PyYAML mysqlclient
	% ~/.local/uvicorn-python3.13/bin/uvicorn Main:Display_history --host LAN_IP --port 60081 --reload

Now the history should also be accessible at:

	http://LAN_IP:60081/chan/server_id/chan_id

# Import a user base from HelloAsso

A script is provided to import CSV files supplied by HelloAsso.

	% cd harmonia/utils
	% for File in Config_manager.py Config.yaml DB_manager.py ; ln -s ../$File
	% chmod +x Import_HelloAsso_CSV.py
	% for File in *csv ; ./Import_HelloAsso_CSV.py $File
