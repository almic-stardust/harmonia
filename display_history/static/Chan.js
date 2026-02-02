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

function Is_file_an_image(Path){
	if (!Path)
		return false;
	return /\.(png|jpe?g|gif|webp)$/i.test(Path);
}

function File_icon(Path){
	Icon = "📎";
	if (!Path)
		return Icon;
	const Extension = Path.split(".").pop().toLowerCase();
	if (Extension === "pdf")
		Icon = "📄";
	if (Extension === "zip" || Extension === "rar" || Extension === "7z")
		Icon = "🗜️";
	if (Extension === "txt")
		Icon = "📃";
	return Icon;
}

function Create_message_element(Message, Date_object){
	const Date_message = Format_date(Date_object);

	let HTML_attachments = "";
	if (Message.attachments !== null){
		let Files = [];
		try{
			// We do “|| []” to prevent the Files variable from becoming null
			Files = JSON.parse(Message.attachments) || [];
		}catch(Error){
			Files = [];
		}
		if (Array.isArray(Files) && Files.length){
			const Image_files = Files.filter(File => Is_file_an_image(File));
			const Other_files = Files.filter(File => !Is_file_an_image(File));
			HTML_attachments = `<div class="attachments">`;
			// Just one image = max-height 350px
			if (Image_files.length == 1 && !Other_files.length)
				Image_class = "one_image";
			// Multiple images, or one image and other file(s) = 150x150px thumbnails
			else
				Image_class = "multiple_images";
			if (Image_files.length){
				let HTML_images = "";
				Image_files.forEach(File => {
					let Hover_name = File.split("/").pop();
					// If the filename starts with “YYYYMMDD—”, don’t display it on hover
					Hover_name = Hover_name.replace(/^\d{8}—/, "");
					Hover_name = Hover_name.replace(/_/g, " ");
					// Remove extension
					Hover_name = Hover_name.replace(/\.[^.]+$/, "");
					Hover_name = Escape_HTML(Hover_name);
					HTML_images += `<img src="/attachments/${encodeURI(File)}"
							title="${Hover_name}" loading="lazy">`;
				});
				HTML_attachments += `<div class="${Image_class}">${HTML_images}</div>`;
			}
			// Non-image files
			if (Other_files.length){
				let HTML_files = `<div class="file_attachments">`;
				Other_files.forEach(File => {
					const Icon = File_icon(File);
					const Filename = File.split("/").pop();
					const Hover_name = Escape_HTML(Filename);
					let Displayed_name = Filename.replace(/^\d{8}—/, "");
					// Limit displayed filename to 30 characters (add ellipsis if truncated)
					if (Displayed_name.length > 30)
						Displayed_name = Displayed_name.slice(0, 29) + "…";
					// Escape_HTML last, so as not to cut inside entities like &amp;
					Displayed_name = Escape_HTML(Displayed_name);
					HTML_files += `
						<a class="file_attachment" href="/attachments/${encodeURI(File)}"
								target="_blank">
							<span class="file_icon">${Icon}</span>
							<span class="file_name" title="${Hover_name}">
								&nbsp;${Displayed_name}
							</span>
						</a>
					`;
				});
				HTML_files += `</div>`;
				HTML_attachments += HTML_files;
			}
			HTML_attachments += `</div>`;
		}
	}

	const Div = document.createElement("div");
	Div.className = "message";
	Div.innerHTML = `
		<div class="metadata">
			<span class="time"
				title="${Date_message.Full_timestamp}">${Date_message.Time_part}
			</span>
			<span class="user">${Escape_HTML(Message.user_name)}</span>
		</div>
		<div class="content_block">
			<span class="content">${Normalize_content(Message.content || "")}</span>
			${HTML_attachments}
		</div>
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

	// Set scroll position so the view doesn’t jump. Use requestAnimationFrame twice to wait for
	// full layout
	requestAnimationFrame(() => {
		requestAnimationFrame(() => {
			if (Initial)
				New_scroll_height = document.body.scrollHeight;
			else
				New_scroll_height = document.body.scrollHeight - Old_scroll_height;
			window.scrollTo(0, New_scroll_height);
		});
	});

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

// Lightbox to show images fullscreen
const Lightbox = document.getElementById("lightbox");
const LB_image = document.getElementById("lightbox_image");
let LB_images = [];
let LB_index = -1;
let LB_zoom = 1;
let LB_offset_X = 0;
let LB_offset_Y = 0;
let LB_dragging = false;
let LB_drag_start_X = 0;
let LB_drag_start_Y = 0;
function Close_lightbox(){
	Lightbox.style.display = "none";
	LB_image.src = "";
	LB_image.style.transform = "";
	document.body.classList.remove("no_scroll");
}

// Zoom in the lightbox
Lightbox.addEventListener("wheel", (Event) => {
	Event.preventDefault();
	// Zoom step
	const Zoom_factor = 0.1;
	// Scroll up: zoom in
	if (Event.deltaY < 0)
		LB_zoom *= 1 + Zoom_factor;
	// Scroll down: zoom out
	else
		LB_zoom /= 1 + Zoom_factor;
	// Limit the zoom to 10 levels
	LB_zoom = Math.min(Math.max(LB_zoom, 1), 10);
	// Update view with current offsets
	LB_image.style.transform = `translate(${LB_offset_X}px, ${LB_offset_Y}px) scale(${LB_zoom})`;
}, { passive: false });

// Panning in lightbox with mouse drag
LB_image.addEventListener("mousedown", (Event) => {
	Event.preventDefault();
	LB_dragging = true;
	LB_drag_start_X = Event.clientX - LB_offset_X;
	LB_drag_start_Y = Event.clientY - LB_offset_Y;
});
LB_image.addEventListener("mousemove", (Event) => {
	if (!LB_dragging)
		return;
	LB_offset_X = Event.clientX - LB_drag_start_X;
	LB_offset_Y = Event.clientY - LB_drag_start_Y;
	LB_image.style.transform = `translate(${LB_offset_X}px, ${LB_offset_Y}px) scale(${LB_zoom})`;
});
LB_image.addEventListener("mouseup", () => {
	LB_dragging = false;
});

// Close the lightbox on double-click
Lightbox.addEventListener("dblclick", () => {
	Close_lightbox();
});

// Mouse events
Container.addEventListener("click", Event => {
	// If an image is clicked, show it fullscreen in a lightbox
	if (Event.target.tagName === "IMG"){
		// Find parent message
		const Message_div = Event.target.closest(".message");
		if (!Message_div)
			return;
		// If the message contains multiple images, activate navigation with PageUp and PageDown
		LB_images = Array.from(
			Message_div.querySelectorAll(".one_image img, .multiple_images img")
		);
		LB_index = LB_images.indexOf(Event.target);
		if (LB_index === -1)
			return;
		document.body.classList.add("no_scroll");
		LB_image.src = Event.target.src;
		Lightbox.style.display = "flex";
		// Reset zoom and pan
		LB_image.style.transform = `translate(0px, 0px) scale(1)`;
		LB_zoom = 1;
		LB_offset_X = 0;
		LB_offset_Y = 0;
	}
});

// Keyboard shortcuts
document.addEventListener("keydown", Event => {
	if (Lightbox.style.display !== "flex")
		return;
	if (Event.key === "PageDown" || Event.key === " ") {
		// Wrap-around (last → first and first ← last)
		LB_index = (LB_index + 1) % LB_images.length;
		LB_zoom = 1;
		LB_offset_X = 0;
		LB_offset_Y = 0;
		LB_image.style.transform = "";
		LB_image.src = LB_images[LB_index].src;
		Event.preventDefault();
	}
	if (Event.key === "PageUp" || Event.key === "Backspace") {
		LB_index = (LB_index - 1 + LB_images.length) % LB_images.length;
		LB_zoom = 1;
		LB_offset_X = 0;
		LB_offset_Y = 0;
		LB_image.style.transform = "";
		LB_image.src = LB_images[LB_index].src;
		Event.preventDefault();
	}

	// Panning when the lightbox is zoomed
	const Pan_step = 50; // Each key press move the image of Pan_step pixels
	if (LB_zoom > 1) {
		switch (Event.key) {
			case "ArrowUp":
				LB_offset_Y += Pan_step;
				break;
			case "ArrowDown":
				LB_offset_Y -= Pan_step;
				break;
			case "ArrowLeft":
				LB_offset_X += Pan_step;
				break;
			case "ArrowRight":
				LB_offset_X -= Pan_step;
				break;
		}
		LB_image.style.transform = `translate(${LB_offset_X}px, ${LB_offset_Y}px) scale(${LB_zoom})`;
		Event.preventDefault();
	}

	// Close lightbox
	if (Event.key === "Escape"){
		Close_lightbox();
		Event.preventDefault();
	}
});

// Load the last 50 messages
Load_messages(true);

})();
