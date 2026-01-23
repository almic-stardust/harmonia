(() => {
	const Container = document.getElementById("messages");
	if (!Container)
		return;
	// Prevent concurrent loads when scrolling hits the top repeatedly
	let Is_loading = false;
	// Cursor used when fetching messages older than the currently oldest one
	let Next_cursor = Container.dataset.nextCursor || null;

	// DOM-based HTML escape
	function Escape_HTML(Text){
		const Div = document.createElement("div");
		Div.textContent = Text;
		return Div.innerHTML;
	}

	// Trim whitespaces and preserve line breaks
	function Normalize_content(Text){
		return Escape_HTML(Text.trim()).replace(/\n/g, "<br>");
	}

	function Create_message_element(Message){
		// Normalize timestamp format between:
		// - space-separated, for server-side rendering of the 50 initial messages
		// - T-separated ISO-like, for JavaScript rendering of autoloaded older messages
		const Date_time = (Message.Date_creation || "").replace("T", " ");
		const [Date_part, Time_part] = Date_time.split(" ");
		// Display only HH:MM in the message list
		let Display_time = "";
		if (Time_part){
			Display_time = Time_part.split(":").slice(0, 2).join(":");
		}
		// Display date as DD/MM/YYYY
		let Display_date = "";
		if (Date_part){
			const [Year, Month , Day] = Date_part.split("-");
			Display_date = `${Day}/${Month}/${Year}`;
		}
		// Full timestamp shown on hover
		const Tool_tip = `${Display_date} ${Time_part || ""}`.trim();

		const Div = document.createElement("div");
		Div.className = "message";
		Div.innerHTML = `
			<div class="meta">
				<span class="time" title="${Tool_tip}">${Display_time}</span>
				<span class="user">${Escape_HTML(Message.User_name)}</span>
			</div>
			<span class="content">${Normalize_content(Message.Content)}</span>
		`;
		return Div;
	}

	function Hydrate_initial_messages(){
		// Convert server-side rendered messages into the same DOM structure used by dynamically
		// loaded ones
		const Raw_nodes = Array.from(Container.children);
		// Clear original HTML to avoid duplication
		Container.innerHTML = "";

		Raw_nodes.forEach(Node => {
			const Message = {
				Message_id: Node.dataset.messageId,
				User_name: Node.dataset.userName,
				Date_creation: Node.dataset.dateCreation,
				Edited:
					Node.dataset.edited !== "false" &&
					Node.dataset.edited !== "0" &&
					Node.dataset.edited !== "",
				Reply_to: Node.dataset.replyTo || null,
				Date_deletion: Node.dataset.dateDeletion || null,
				Content: Node.textContent || ""
			};
			Container.appendChild(Create_message_element(Message));
		});
	}

	async function Load_older_messages(){
		// Abort if already loading or if no more messages are available
		if (Is_loading || !Next_cursor)
			return;
		Is_loading = true;
		// Save current scroll height so we can restore position after prepend
		const Old_scroll_height = document.body.scrollHeight;

		const Params = new URLSearchParams({
			Server_id: Container.dataset.serverId,
			Chan_id: Container.dataset.chanId,
			Before: Next_cursor
		});
		const Response = await fetch(`/api/messages?${Params.toString()}`);
		if (!Response.ok){
			Is_loading = false;
			return;
		}
		const Data = await Response.json();

		// Stop requesting if no more messages are returned
		if (!Data.Messages || !Data.Messages.length){
			Next_cursor = null;
			Is_loading = false;
			return;
		}

		// Build messages in a document fragment to avoid repeated reflows
		const Fragment = document.createDocumentFragment();
		Data.Messages.forEach(Raw_message => {
			// Match internal structure
			const Message = {
				Message_id: Raw_message.message_id,
				User_name: Raw_message.user_name,
				Date_creation: Raw_message.date_creation,
				Edited: Raw_message.edited,
				Reply_to: Raw_message.reply_to,
				Date_deletion: Raw_message.date_deletion,
				Content: Raw_message.content || ""
			};
			Fragment.appendChild(Create_message_element(Message));
		});
		// Prepend older messages at the top
		Container.prepend(Fragment);

		// Update cursor to fetch the next batch later
		Next_cursor = Data.Next_cursor;
		// Restore scroll position so the view doesn’t jump
		const New_scroll_height = document.body.scrollHeight;
		window.scrollTo(0, New_scroll_height - Old_scroll_height);
		Is_loading = false;
	}

	document.addEventListener("DOMContentLoaded", () => {
		// Rebuild initial messages so that SSR and JS rendering matches
		Hydrate_initial_messages();
		// Wait until layout height stabilizes before auto-scrolling to bottom
		let Last_height = 0;
		let Stable_frames = 0;
		function Scroll_when_stable(){
			const Current_height = document.body.scrollHeight;
			if (Current_height === Last_height){
				Stable_frames++;
				if (Stable_frames >= 2){
					window.scrollTo(0, Current_height);
					return;
				}
			}
			else {
				Stable_frames = 0;
				Last_height = Current_height;
			}
			requestAnimationFrame(Scroll_when_stable);
		}
		requestAnimationFrame(Scroll_when_stable);
	});

	window.addEventListener("scroll", () => {
		if (window.scrollY <= 5){
			Load_older_messages();
		}
	});

})();
