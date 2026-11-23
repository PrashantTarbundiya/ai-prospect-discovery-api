"use strict";

const byId = (id) => document.getElementById(id);
const query = byId("query");
const submit = byId("submit");
const results = byId("result-content");
const searches = [];
let selected = null;
let busy = false;

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text != null) el.textContent = text;
  return el;
}

function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", "#" + name);
  svg.setAttribute("aria-hidden", "true");
  svg.append(use);
  return svg;
}

function message(title, description, symbol, loading = false) {
  const box = element("div", loading ? "empty loading" : "empty");
  const tile = element("span", "empty-icon");
  tile.append(icon(symbol));
  const copy = element("div");
  copy.append(element("h3", "", title), element("p", "", description));
  box.append(tile, copy);
  return box;
}

function publicLink(item) {
  let url;
  try {
    url = new URL(item.link);
  } catch {
    return null;
  }
  const allowed = item.platform === "Email" ? ["mailto:"] :
    item.platform === "Phone" ? ["tel:"] : ["https:", "http:"];
  if (!allowed.includes(url.protocol)) return null;
  const isContact = ["Email", "Phone"].includes(item.platform);
  const label = isContact ? item.link.slice(url.protocol.length) : item.platform;
  const anchor = element("a", "profile-link", label);
  anchor.href = url.href;
  anchor.title = item.platform + " · " + item.link;
  if (!isContact) {
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
  }
  return anchor;
}

function profileCard(prospect, isPersonSearch) {
  const row = element("li", "profile");
  const initials = prospect.name.trim().split(/\s+/).slice(0, 2).map(word => Array.from(word)[0]).join("");
  const avatar = element("span", "initials", initials.toUpperCase());
  avatar.setAttribute("aria-hidden", "true");
  const body = element("div", "profile-body");
  body.append(element("h3", "", prospect.name));
  if (isPersonSearch && prospect.social_link.length) {
    const source = publicLink(prospect.social_link[0]);
    if (source) {
      source.className = "profile-source";
      source.textContent = source.href.replace(/^https?:\/\//, "");
      body.append(source);
    }
  }
  if (prospect.description) body.append(element("p", "profile-description", prospect.description));
  if (prospect.location) {
    const location = element("p", "location");
    location.append(icon("pin"), document.createTextNode(prospect.location));
    body.append(location);
  }
  const links = element("div", "link-list");
  prospect.social_link.forEach(item => {
    const link = publicLink(item);
    if (link) links.append(link);
  });
  body.append(links);
  row.append(avatar, body);
  return row;
}

function renderResult(entry) {
  selected = entry;
  const data = entry.data;
  const badge = byId("result-count");
  badge.textContent = String(data.total_prospects);
  badge.hidden = false;
  byId("export").hidden = false;
  results.replaceChildren(element("p", "query-summary", data.query));
  byId("results-heading").textContent = entry.mode === "person" ? "Matching profiles" : "Prospect results";
  if (entry.unavailable) {
    results.append(element("p", "notice", "Partial coverage. Unavailable sources: " + entry.unavailable + "."));
  }
  if (data.prospects.length === 0) {
    const help = entry.mode === "person"
      ? "Try the spelling used on the public profile, or search for its @handle."
      : "Try a broader audience or a different location.";
    results.append(message("No matching profiles", help, "search"));
    return;
  }
  const list = element("ul", "profile-list");
  list.append(...data.prospects.map(prospect => profileCard(prospect, entry.mode === "person")));
  results.append(list);
}

function updateQuery() {
  byId("count").textContent = query.value.length + " / 400";
  query.setCustomValidity("");
  byId("form-error").hidden = true;
}

function searchMode() {
  return byId("query-form").elements.mode.value;
}

function syncMode() {
  const person = searchMode() === "person";
  byId("query-label").textContent = person ? "Full name or @handle" : "Enter a topic or audience";
  query.placeholder = person ? "e.g. Guido van Rossum" : "e.g. Startup founders in London";
  if (!busy) submit.querySelector("span").textContent = person ? "Find profiles" : "Discover prospects";
  document.querySelectorAll("[data-query]").forEach(button => {
    button.hidden = (button.dataset.mode || "discovery") !== searchMode();
  });
  updateQuery();
}
document.querySelectorAll('input[name="mode"]').forEach(input => input.addEventListener("change", syncMode));

function showHistory() {
  const list = byId("history-list");
  list.replaceChildren();
  if (!searches.length) {
    list.append(message("No searches yet", "Completed searches stay here until you refresh or close this tab.", "clock"));
    return;
  }
  searches.forEach(entry => {
    const button = element("button", "history-row");
    button.type = "button";
    button.disabled = busy;
    const n = entry.data.total_prospects;
    button.append(element("strong", "", entry.data.query),
      element("span", "history-meta", entry.time + " · " + n + (n === 1 ? " prospect" : " prospects")));
    button.addEventListener("click", () => {
      byId("query-form").elements.mode.value = entry.mode;
      syncMode();
      query.value = entry.data.query;
      updateQuery();
      renderResult(entry);
      location.hash = "discovery";
      requestAnimationFrame(() => byId("results").scrollIntoView({block: "center"}));
    });
    list.append(button);
  });
}

function navigate() {
  const history = location.hash === "#history";
  byId("workspace").hidden = history;
  byId("history").hidden = !history;
  [[byId("discover-tab"), !history], [byId("history-tab"), history]].forEach(([link, active]) => {
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  document.title = (history ? "History" : "Discovery") + " · Fieldwork";
  if (history) showHistory();
}

query.addEventListener("input", updateQuery);
query.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    byId("query-form").requestSubmit();
  }
});
document.querySelectorAll("[data-query]").forEach(button => {
  button.addEventListener("click", () => {
    query.value = button.dataset.query;
    updateQuery();
    query.focus();
  });
});

byId("query-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (busy) return;
  const text = query.value.trim();
  const mode = searchMode();
  if (!/\p{L}/u.test(text)) {
    query.setCustomValidity("Enter a search containing at least one letter.");
    query.reportValidity();
    return;
  }
  busy = true;
  submit.disabled = true;
  submit.querySelector("span").textContent = "Searching…";
  selected = null;
  byId("results-heading").textContent = mode === "person" ? "Matching profiles" : "Prospect results";
  byId("result-count").hidden = true;
  byId("export").hidden = true;
  byId("form-error").hidden = true;
  results.replaceChildren(message("Searching public profiles", "Checking sources for “" + text + "”…", "compass", true));
  try {
    const response = await fetch("/prospect-discovery", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({query: text, mode})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const validation = Array.isArray(data.detail) ? data.detail.map(item => item.msg).filter(Boolean).join(" ") : "";
      const detail = typeof data.detail === "string" ? data.detail :
        validation || "The discovery request failed (HTTP " + response.status + "). Try again.";
      throw new Error(detail);
    }
    if (!data.success || !Array.isArray(data.prospects)) throw new Error("The server returned an incomplete result.");
    const entry = {data, mode, unavailable: response.headers.get("X-Unavailable-Sources"),
      time: new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})};
    searches.unshift(entry);
    if (searches.length > 20) searches.pop();
    renderResult(entry);
    if (!byId("workspace").hidden) byId("results").scrollIntoView({block: "start"});
  } catch (error) {
    const detail = error instanceof TypeError ? "Could not reach the local server. Check that the app is running." : error.message;
    results.replaceChildren(message("Search unsuccessful", detail, "search"));
    const feedback = byId("form-error");
    feedback.textContent = detail;
    feedback.hidden = false;
  } finally {
    busy = false;
    submit.disabled = false;
    submit.querySelector("span").textContent = searchMode() === "person" ? "Find profiles" : "Discover prospects";
    if (!byId("history").hidden) showHistory();
  }
});

byId("export").addEventListener("click", () => {
  if (!selected) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(selected.data, null, 2)], {type: "application/json"}));
  const link = element("a");
  link.href = url;
  link.download = "prospect-results.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
});
window.addEventListener("hashchange", navigate);
syncMode();
navigate();
