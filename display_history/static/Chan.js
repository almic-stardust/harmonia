(() => {

const Container = document.getElementById("messages");
if (!Container)
	return;
// Retrieve variables from URL: domain.tld/chan/<Server_ID>/<Chan_ID>
const Path = window.location.pathname.split("/");
const Server_ID = Path[2];
const Chan_ID = Path[3];
// Prevent concurrent loads when the user scrolls quickly and hits the top repeatedly
let Is_loading = false;
// Cursor used when fetching messages older than the currently oldest one
let Next_cursor = null;
// Date of the message at the top of the page
let Date_top_page = null;

function Extract_date(Date_creation){
	if (!Date_creation)
		return null;
	// Normalize timestamp format between space-separated and T-separated
	const Date_time = Date_creation.replace("T", " ");
	// Return YYYY-MM-DD
	return Date_time.split(" ")[0];
}

function Format_date(Date_part){
	if (!Date_part)
		return null;
	// Date_part has the format YYYY-MM-DD
	const [Year, Month, Day] = Date_part.split("-");
	return `${Day}/${Month}/${Year}`;
}

function Create_date_separator(Date_part){
	const Div = document.createElement("div");
	Div.className = "date_separator";
	Div.textContent = Format_date(Date_part);
	return Div;
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
	const Date_time = (Message.date_creation || "").replace("T", " ");
	const [Date_part, Time_part] = Date_time.split(" ");
	// Display time as HH:MM
	let Display_time = "";
	if (Time_part)
		Display_time = Time_part.split(":").slice(0, 2).join(":");
	// Display date as DD/MM/YYYY
	let Display_date = "";
	if (Date_part)
		Display_date = Format_date(Date_part)
	// Full timestamp shown on hover
	const Tool_tip = `${Display_date} ${Time_part || ""}`;

	const Div = document.createElement("div");
	Div.className = "message";
	Div.innerHTML = `
		<div class="meta">
			<span class="time" title="${Tool_tip}">${Display_time}</span>
			<span class="user">${Escape_HTML(Message.user_name)}</span>
		</div>
		<span class="content">${Normalize_content(Message.content || "")}</span>
	`;
	return Div;
}

// Loads the initial batch (Initial=true), or older messages when scrolling up
async function Load_messages(Initial=false){
	// Abort if already loading. Or abort if no more messages to load (meaning if Next_cursor is
	// null even though it’s no longer the first call)
	if (Is_loading || (!Initial && Next_cursor === null))
		return;
	Is_loading = true;

	const Params = new URLSearchParams({
		Server_ID,
		Chan_ID
	});
	if (!Initial)
		Params.append("Before", Next_cursor);

    // Save current scroll height so we can restore position after prepending the older messages
	const Old_scroll_height = document.body.scrollHeight;

	const Response = await fetch(`/api/messages?${Params}`);
	if (!Response.ok){
		Is_loading = false;
		return;
	}
	const Data = await Response.json();
	// If no messages are returned, the history is exhausted
	if (!Data.Messages || !Data.Messages.length){
		Next_cursor = null;
		Is_loading = false;
		window.removeEventListener("scroll", Load_messages);
		return;
	}

	// Build messages in a document fragment to avoid repeated layout recalculations
	const Fragment = document.createDocumentFragment();

    // Determine the date of the newest and oldest message in this batch
	const Date_top_batch = Extract_date(Data.Messages[0].date_creation);
	const Date_bottom_batch = Extract_date(Data.Messages.at(-1).date_creation);
	let Date_previous_message = Date_top_batch;

	Data.Messages.forEach(Message => {
		// Insert the date separators when needed, inside the batch
		const Date_current_message = Extract_date(Message.date_creation);
		if (Date_current_message !== Date_previous_message)
			Fragment.appendChild(Create_date_separator(Date_current_message));
		Date_previous_message = Date_current_message;

		Fragment.appendChild(Create_message_element(Message));
	});

	// Since messages are displayed from oldest to newest, but the batches are added at the top of
	// the page:
	// - date changes can be detected within a batch
	// - however, this non-linear order requires managing separately the date changes between the
	//   batches.
	// So we check if the date has changed between the message previously at the top of the page,
	// and the message at the bottom of the current batch. And if that’s the case, we insert a date
	// separator at the end of the current batch.
    // Unless it’s the initial load, because in that case Date_top_page will be null.
	if (!Initial && Date_bottom_batch !== Date_top_page)
		Fragment.appendChild(Create_date_separator(Date_bottom_batch));

	// Prepend the batch of older messages at the top
	Container.prepend(Fragment);

	// Restore scroll position so the view doesn’t jump
	if (Initial)
		window.scrollTo(0, document.body.scrollHeight);
	else
		window.scrollTo(0, document.body.scrollHeight - Old_scroll_height);
	// Update cursor for the next request
	Next_cursor = Data.Next_cursor;
	// Update the date of the message now at the top of the page
	Date_top_page = Date_top_batch;
	Is_loading = false;
}

// When the user scrolls near the top, load older messages
window.addEventListener("scroll", () => {
	if (window.scrollY <= 5)
		Load_messages();
});

// Load the last 50 messages
Load_messages(true);

})();
