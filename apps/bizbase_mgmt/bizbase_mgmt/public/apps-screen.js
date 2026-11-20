// Desk translates the visible caption after bootinfo has supplied each app's title.
// Keep the published names on the Apps grid in every Desk language.
$(document).on("desktop_screen", (_event, { desktop }) => {
	const titles = new Set(["CRM", "ERP", "Build", "Insights"]);
	for (const card of desktop.wrapper[0].querySelectorAll(".desktop-icon")) {
		const title = card.querySelector("img.app-icon")?.alt;
		const link = card.querySelector(".icon-title");
		if (link && titles.has(title)) {
			link.textContent = title;
			link.setAttribute("data-original-title", title);
		}
	}
});
