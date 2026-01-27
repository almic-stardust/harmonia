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
let UTaM_top_page = null;

// Convert a UTC timestamp string from the DB to a Date object in the browser’s local timezone
function DB_to_local_time(DB_date){
	if (!DB_date)
		return null;
	// We add “Z” because the time is stored in UTC in the DB
	// “2025-12-24 02:00:00” will be interpreted as local time
	// “2025-12-24T02:00:00Z” will be converted from UTC
	const UTC_date = new Date(DB_date + "Z");
	if (isNaN(UTC_date.getTime()))
		return null;
	return new Date(
		UTC_date.getFullYear(), UTC_date.getMonth(), UTC_date.getDate(),
		UTC_date.getHours(), UTC_date.getMinutes(), UTC_date.getSeconds()
	);
}

function Unix_time_at_midnight(Date_object){
	if (!(Date_object instanceof Date) || isNaN(Date_object.getTime()))
		return null;
	// A Date object corresponding to that day at midnight
	Calendar_date = new Date(
			Date_object.getFullYear(), Date_object.getMonth(), Date_object.getDate())
	// getTime() returns the time between Unix epoch and that day at midnight, in milliseconds.
	// Since we want to speed up comparisons, we can divide by 1000 to get a Unix time in seconds,
	// and again by 100, because a Unix time at midnight will always end with two 0.
	// Math.floor() remove the fractional part, which allow comparison of ints rather than floats.
	return Math.floor(Calendar_date.getTime()/100000)
}

function Format_date(Date_object){
	if (!(Date_object instanceof Date) || isNaN(Date_object.getTime()))
		return {Date_part: "", Time_part: "", Full_timestamp: ""};
	const Year		= Date_object.getFullYear();
	const Month		= String(Date_object.getMonth() + 1).padStart(2, "0");
	const Day		= String(Date_object.getDate()).padStart(2, "0");
	const Hour		= String(Date_object.getHours()).padStart(2, "0");
	const Minutes	= String(Date_object.getMinutes()).padStart(2, "0");
	const Seconds	= String(Date_object.getSeconds()).padStart(2, "0");
	const Date_part = `${Day}/${Month}/${Year}`;
	const Time_part = `${Hour}:${Minutes}`;
	const Full_timestamp = `${Date_part} ${Hour}:${Minutes}:${Seconds}`;
	return {Date_part, Time_part, Full_timestamp};
}

function Create_date_separator(Date_object){
	const Div = document.createElement("div");
	Div.className = "date_separator";
	Div.textContent = Format_date(Date_object).Date_part;
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

function Create_message_element(Message, Date_object){
	const Date_message = Format_date(Date_object);
	const Div = document.createElement("div");
	Div.className = "message";
	Div.innerHTML = `
		<div class="meta">
			<span class="time"
				title="${Date_message.Full_timestamp}">${Date_message.Time_part}
			</span>
			<span class="user">${Escape_HTML(Message.user_name)}</span>
		</div>
		<span class="content">${Normalize_content(Message.content || "")}</span>
	`;
	return Div;
}

// Loads either the initial batch (Initial=true), or older messages when scrolling up
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

	// Determine UTaM (Unix Time at Midnight) of the first and last messages of this batch
	const UTaM_top_batch = Unix_time_at_midnight(DB_to_local_time(Data.Messages[0].date_creation));
	// We reuse Date_bottom_batch. No need for a Date_top_batch variable since it wouldn’t be reused
	const Date_bottom_batch = DB_to_local_time(Data.Messages.at(-1).date_creation);
	const UTaM_bottom_batch = Unix_time_at_midnight(Date_bottom_batch);
	let UTaM_previous_message = UTaM_top_batch;

	Data.Messages.forEach(Message => {
		// Insert the date separators when needed, inside the current batch
		const Date_current_message = DB_to_local_time(Message.date_creation);
		const UTaM_current_message = Unix_time_at_midnight(Date_current_message);
		if (UTaM_current_message !== UTaM_previous_message)
			Fragment.appendChild(Create_date_separator(Date_current_message));
		UTaM_previous_message = UTaM_current_message;

		Fragment.appendChild(Create_message_element(Message, Date_current_message));
	});

	// Since messages are displayed from oldest to newest, but the batches are added at the top of
	// the page:
	// - date changes can be detected within a batch
	// - however, this non-linear order requires managing separately the date changes between the
	//   batches.
	// So we check if the date has changed between the message previously at the top of the page,
	// and the message at the bottom of the current batch. And if that’s the case, we insert a date
	// separator at the end of the current batch.
	// Unless it’s the initial load, because in that case UTaM_top_page will be null.
	if (!Initial && UTaM_bottom_batch !== UTaM_top_page)
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
	UTaM_top_page = UTaM_top_batch;
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
