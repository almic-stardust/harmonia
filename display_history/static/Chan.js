(() => {

const Container = document.getElementById("messages");
if (!Container)
	return;
// Prevent concurrent loads when scrolling hits the top repeatedly
let Is_loading = false;
// Cursor used when fetching messages older than the currently oldest one
let Next_cursor = Container.dataset.nextCursor || null;
// Date of the message at the top of the page
let Date_top_page = null;

function Extract_day(Date_creation){
	if (!Date_creation)
		return null;
	// Normalize timestamp format between space-separated and T-separated
	const Date_time = Date_creation.replace("T", " ");
	// Return YYYY-MM-DD
	return Date_time.split(" ")[0];
}

function Format_day(Date_part){
	// Date_part has the format YYYY-MM-DD
	const [Year, Month, Day] = Date_part.split("-");
	return `${Day}/${Month}/${Year}`;
}

function Create_day_separator(Date_part){
	const Div = document.createElement("div");
	Div.className = "day_separator";
	Div.textContent = Format_day(Date_part);
	return Div;
}

function Get_message_day(Message_element){
	const Time = Message_element.querySelector(".time");
	if (!Time || !Time.title)
		return null;
	const [Date_part] = Time.title.split(" ");
	return Date_part ? Date_part.split("/").reverse().join("-") : null;
}

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
	// Display time as HH:MM
	let Display_time = "";
	if (Time_part)
		Display_time = Time_part.split(":").slice(0, 2).join(":");
	// Display date as DD/MM/YYYY
	let Display_date = "";
	if (Date_part)
		Display_date = Format_day(Date_part)
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
	let Date_previous_message = null;

	Raw_nodes.forEach((Node, Index) => {
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

		// Day separator management
		const Current_day = Extract_day(Message.Date_creation);
		if (Index === 0)
			Date_top_page = Current_day;
		else if (Current_day !== Date_previous_message)
			Container.appendChild(Create_day_separator(Current_day));
		Date_previous_message = Current_day;

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

	// Day separator management
	let Date_top_batch = Extract_day(Data.Messages[0].date_creation);
	let Index_bottom_message = Data.Messages.length - 1
	let Date_bottom_batch = Extract_day(Data.Messages[Index_bottom_message].date_creation);
	// Before inserting any message, check for day change
	if (Date_top_page !== null && Date_bottom_batch !== Date_top_page)
		Fragment.appendChild(Create_day_separator(Date_bottom_batch));
	let Date_previous_message = Date_top_batch;

	Data.Messages.forEach((Raw_message, Index) => {
		const Is_last = (Index === Data.Messages.length - 1);

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

		// Day separator management
		const Current_day = Extract_day(Message.Date_creation);
		if (!Is_last && Current_day !== Date_previous_message)
			Fragment.appendChild(Create_day_separator(Current_day));
		Date_previous_message = Current_day;

		Fragment.appendChild(Create_message_element(Message));
	});

	// Prepend older messages at the top
	Container.prepend(Fragment);

	// Restore scroll position so the view doesn’t jump
	const New_scroll_height = document.body.scrollHeight;
	window.scrollTo(0, New_scroll_height - Old_scroll_height);
	// Update cursor to fetch the next batch later
	Next_cursor = Data.Next_cursor;
	// Update the day of the message at the top of the page
	Date_top_page = Date_top_batch;
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
	if (window.scrollY <= 5)
		Load_older_messages();
});

})();
