"use strict";

// =========================================================================
// HW1 - form validation and JS language features
// =========================================================================

// Validating the form using arrow function
const validateForm = () => {
    const description = document.getElementById("description").value.trim();
    const agreeTerms = document.getElementById("agreeTerms").checked;

    if (description.length <= 25) {
        alert("Incident description must be more than 25 characters.");
        return false;
    }
    if (!agreeTerms) {
        alert("You must agree to the terms and conditions before submitting.");
        return false;
    }
    return true;
}

// Closure for tracking the number of successful form submissions
const submissionCounter = (() => {
  let count = 0;
  return () => ++count;
})();

// =========================================================================
// HW2 - REST calls against the FastAPI backend on PORT_BASE
// =========================================================================

const API = "/api/incidents";

const el = (id) => document.getElementById(id);

/** Show exactly one of the list states; hide the other three. */
const showState = (which, detail = "") => {
  const panes = {
    loading: el("listLoading"),
    empty: el("listEmpty"),
    error: el("listError"),
    list: el("incidentList"),
  };
  Object.entries(panes).forEach(([name, node]) => {
    node.hidden = name !== which;
  });
  if (which === "error") {
    el("listErrorDetail").textContent = detail;
  }
};

/** Fetch + JSON, turning a non-2xx into a throw so callers have one error path. */
const requestJSON = async (url, options = {}) => {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && body.detail) {
        // FastAPI validation errors arrive as an array of objects.
        detail = typeof body.detail === "string"
          ? body.detail
          : body.detail.map((d) => d.msg).join("; ");
      }
    } catch (ignored) { /* keep the status-line fallback */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
};

const renderIncidents = (items) => {
  const list = el("incidentList");
  list.innerHTML = "";

  if (!items.length) {
    showState("empty");
    return;
  }

  items.forEach((incident) => {
    const li = document.createElement("li");

    const head = document.createElement("div");
    head.className = "incident-head";
    // textContent, not innerHTML: incident text is user-submitted.
    const route = document.createElement("span");
    route.textContent = incident.routeId;
    const id = document.createElement("span");
    id.className = "incident-id";
    id.textContent = `#${incident.id}`;
    head.append(route, id);

    const meta = document.createElement("div");
    meta.className = "incident-meta";
    meta.textContent = `${incident.location} · ${incident.category}`;

    const body = document.createElement("div");
    body.textContent = incident.description;

    li.append(head, meta, body);
    list.appendChild(li);
  });

  showState("list");
};

/** Load the list and render it. This is the "home view" everything returns to. */
const loadIncidents = async (searchTerm = "") => {
  showState("loading");
  try {
    const query = searchTerm.trim()
      ? `?search=${encodeURIComponent(searchTerm.trim())}`
      : "";
    const items = await requestJSON(`${API}${query}`);
    renderIncidents(items);
    if (!items.length && searchTerm.trim()) {
      el("listEmpty").textContent = `No incidents match "${searchTerm.trim()}".`;
    } else {
      el("listEmpty").textContent = "No incidents to show.";
    }
  } catch (error) {
    showState("error", error.message);
  }
};

// =========================================================================
// Form submit - HW1 logging, then HW2 create + redirect to the home view
// =========================================================================

document.getElementById("incidentForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  if (!validateForm()) return;

  const formData = {
    routeId: document.getElementById("routeId").value,
    location: document.getElementById("location").value,
    submitterEmail: document.getElementById("submitterEmail").value,
    description: document.getElementById("description").value,
    category: document.getElementById("category").value,
    agreeTerms: document.getElementById("agreeTerms").checked,
  };

  // Converting form data to a JSON string
  const jsonString = JSON.stringify(formData);
  console.log("Form Data (JSON string):", jsonString);

  const parsed = JSON.parse(jsonString);

  // Destructuring the primary field and email field
  const { routeId, submitterEmail } = parsed;
  console.log("Route/Line:", routeId);
  console.log("Submitter Email:", submitterEmail);

  // Spread operator- adding submissionDate to the parsed object
  const withTimestamp = { ...parsed, submissionDate: new Date().toISOString() };
  console.log("Updated Parsed Object:", withTimestamp);

  // Counting and logging how many times the form has been submitted
  const count = submissionCounter();
  console.log(`Submission count: ${count}`);

  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.textContent = "Reporting…";

  try {
    // agreeTerms is a UI concern, not part of the stored record.
    const { agreeTerms, ...incidentPayload } = parsed;
    await requestJSON(API, { method: "POST", body: JSON.stringify(incidentPayload) });

    document.getElementById("incidentForm").reset();
    document.getElementById("routeId").focus();

    // Redirect to the home view showing the updated list.
    el("searchBox").value = "";
    await loadIncidents();
    el("homeView").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showState("error", `Could not save the incident: ${error.message}`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Report Incident";
  }
});

// =========================================================================
// Search, update, delete
// =========================================================================

el("searchBtn").addEventListener("click", () => loadIncidents(el("searchBox").value));

el("searchBox").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    loadIncidents(el("searchBox").value);
  }
});

el("clearSearchBtn").addEventListener("click", () => {
  el("searchBox").value = "";
  loadIncidents();
});

el("retryBtn").addEventListener("click", () => loadIncidents(el("searchBox").value));

// Update the record with ID 1 to domain-appropriate values, then show the list.
el("updateFirstBtn").addEventListener("click", async () => {
  showState("loading");
  try {
    await requestJSON(`${API}/1`, {
      method: "PUT",
      body: JSON.stringify({
        routeId: "Line 22 (Rerouted)",
        location: "Downtown Transit Center - Bay 4",
        submitterEmail: "rider@example.com",
        description: "Route 22 was rerouted around flooding and now boards at Bay 4 until further notice.",
        category: "Delay",
      }),
    });
    el("searchBox").value = "";
    await loadIncidents();
  } catch (error) {
    showState("error", `Could not update incident #1: ${error.message}`);
  }
});

// Delete the record with the highest ID, then show the list.
el("deleteHighestBtn").addEventListener("click", async () => {
  showState("loading");
  try {
    const highest = await requestJSON("/api/incidents-highest-id");
    if (highest === null) {
      await loadIncidents();
      return;
    }
    await requestJSON(`${API}/${highest}`, { method: "DELETE" });
    el("searchBox").value = "";
    await loadIncidents();
  } catch (error) {
    showState("error", `Could not delete the newest incident: ${error.message}`);
  }
});

// Initial paint of the home view.
loadIncidents();
