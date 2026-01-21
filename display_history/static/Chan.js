(() => {
	const Container = document.getElementById("messages");
	if (!Container) return;

	function Escape_HTML(str) {
		const Div = document.createElement("div");
		Div.textContent = str;
		return Div.innerHTML;
	}

	function Normalize_content(text) {
		return Escape_HTML(text.trim()).replace(/\n/g, "<br>");
	}

	function Create_message_element(Message) {
		const [Date_part, Time_part] = (Message.Date_creation || "").split(" ");
		let Display_time = Time_part ? Time_part.split(":").slice(0,2).join(":") : "";
		let Display_date = "";
		if (Date_part) {
			const [Year, Month , Day] = Date_part.split("-");
			Display_date = `${Day}/${Month}/${Year}`;
		}
		const Tool_tip = `${Display_date} ${Time_part || ""}`.trim();

		const Content_HTML = Message.Date_deletion
			? "<span class='deleted'>Message deleted</span>"
			: `<span class="content">${Normalize_content(Message.Content)}</span>`;

		const Div = document.createElement("div");
		Div.className = "message";
		Div.innerHTML = `
			<div class="meta">
				<span class="time" title="${Tool_tip}">${Display_time}</span>
				<span class="user">${Escape_HTML(Message.User_name)}</span>
			</div>
			${Content_HTML}
		`;
		return Div;
	}

	function Hydrate_initial_messages() {
		const Raw_nodes = Array.from(Container.children);
		Container.innerHTML = "";
		Raw_nodes.forEach(node => {
			const Message = {
				Message_id: node.dataset.messageId,
				User_name: node.dataset.userName,
				Date_creation: node.dataset.dateCreation,
				Edited: node.dataset.edited !== "false" && node.dataset.edited !== "0" && node.dataset.edited !== "",
				Reply_to: node.dataset.replyTo || null,
				Date_deletion: node.dataset.dateDeletion || null,
				Content: node.textContent || ""
			};
			Container.appendChild(Create_message_element(Message));
		});
	}

	document.addEventListener("DOMContentLoaded", Hydrate_initial_messages);
})();
