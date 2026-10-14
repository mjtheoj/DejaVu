const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

let currentUser = null;
let appConfig = null;
let selectedClaimReport = null;
let selectedLostReportForMatchId = null;
let lostReportOptionsRequest = 0;
let reportSubmitting = false;
let claimSubmitting = false;
let selectedEvidenceClaimId = null;
let selectedStorageReportId = null;
let selectedHandoverClaimId = null;
let selectedCloseReportId = null;
let selectedCloseReportType = null;

const CATEGORY_ICONS = {
  stationery: "▤", clothing: "◈", bags_wallets: "▣", accessories: "◇",
  electronics: "⌁", identity_documents: "▧", keys_access: "⌘",
  cash_jewellery: "✧", sports_instruments: "◎", other: "◌"
};
const STATUS_LABELS = {
  open: "Open", awaiting_intake: "Awaiting office intake", available: "Available at office",
  claim_approved: "Awaiting handover", pending: "Under review", disputed: "Disputed · review required",
  needs_more_evidence: "More evidence requested", approved_for_collection: "Ready for handover",
  rejected: "Not approved", returned: "Returned to owner", closed: "Closed", cancelled: "Withdrawn"
};
const escapeHTML = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

function explainError(data, fallback) {
  if (!data || !data.detail) return fallback || "Something went wrong.";
  if (Array.isArray(data.detail)) return data.detail.map((x) => x.msg || "Invalid value").join(" ");
  return String(data.detail);
}

async function api(url, options) {
  const opts = Object.assign({ method: "GET", headers: {} }, options || {});
  if (opts.body && !(opts.body instanceof FormData) && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  if (opts.body && !(opts.body instanceof FormData) && !opts.headers["Content-Type"]) {
    opts.headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, opts);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(explainError(data, "Request failed (" + response.status + ")."));
  return data;
}

function showToast(message, error) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", Boolean(error));
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 4800);
}

function showNotice(message, error) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("error", Boolean(error));
  notice.classList.remove("hidden");
  notice.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function statusLabel(status) {
  return STATUS_LABELS[status] || String(status || "Unknown").replace(/_/g, " ");
}

function statusClass(status) {
  return "status-pill status-" + String(status || "").replace(/[^a-z_]/g, "");
}

function humanDate(value) {
  if (!value) return "Date not specified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function humanDateTime(value) {
  if (!value) return "Time not specified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ");
  return date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function categoryLabel(value) {
  const found = (appConfig.categories || []).find((c) => c.value === value);
  return found ? found.label : (value || "Item");
}

async function loadConfig() {
  appConfig = await api("/api/config");
  const categoryOptions = appConfig.categories.map((category) =>
    '<option value="' + escapeHTML(category.value) + '">' + escapeHTML(category.label) + "</option>"
  ).join("");
  $("#reportCategory").innerHTML = '<option value="">Choose a category</option>' + categoryOptions;
  $("#filterCategory").innerHTML = '<option value="">All categories</option>' + categoryOptions;
  const blocks = appConfig.locations.blocks || [];
  const blockOptions = blocks.map((block) =>
    '<option value="' + escapeHTML(block) + '">' + escapeHTML(block) + "</option>"
  ).join("");
  $("#reportBlock").innerHTML = '<option value="">Choose a block or area</option>' + blockOptions;
  $("#filterBlock").innerHTML = '<option value="">All locations</option>' + blockOptions;
  $("#reportFloor").innerHTML = '<option value="">Not sure</option>' + (appConfig.locations.floors || [])
    .map((floor) => '<option value="' + escapeHTML(floor) + '">' + escapeHTML(floor) + "</option>").join("");
  if (appConfig.demo_mode) $("#demoAccess").classList.remove("hidden");
  const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  $("#reportDate").value = localNow.toISOString().slice(0, 16);
}

function showLogin() {
  $("#loginView").classList.remove("hidden");
  $("#appView").classList.add("hidden");
  currentUser = null;
}

function enterApp(user) {
  currentUser = user;
  $("#loginView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
  $("#userName").textContent = user.display_name;
  $("#userInitial").textContent = (user.display_name || "U").trim().charAt(0).toUpperCase();
  $("#userInitial").className = "avatar " + (user.role === "office" ? "avatar-office" : "avatar-student");
  $("#roleChip").textContent = user.role === "office" ? "Office staff" : "Student";
  $("#roleChip").className = "role-chip" + (user.role === "office" ? " role-chip-office" : "");
  $("#officeNavButton").classList.toggle("hidden", user.role !== "office");
  $("#activityNavButton").classList.toggle("hidden", user.role === "office");
  $('[data-view="report"], [data-view="my-reports"], [data-view="my-claims"]').forEach((button) => {
    button.classList.toggle("hidden", user.role === "office");
  });
  $("#welcomeTitle").textContent = user.role === "office" ? "Manage found items and claims." : "Find what you are looking for.";
  $("#welcomeSubtitle").textContent = user.role === "office"
    ? "Confirm physical intake and review claims before authorising the next step."
    : "Search office-held items, compare possible matches and submit a private claim.";
  $("#studentNav").classList.remove("hidden");
  navigate(user.role === "office" ? "office" : "browse");
}

function navigate(view) {
  if (!currentUser) return;
  if (view !== "my-reports") selectedLostReportForMatchId = null;
  if (view === "office" && currentUser.role !== "office") view = "browse";
  if (currentUser.role === "office" && ["report", "my-reports", "my-claims", "activity"].includes(view)) view = "office";
  const sections = {
    browse: "#browseView", report: "#reportView", "my-reports": "#myReportsView",
    "my-claims": "#myClaimsView", notifications: "#notificationsView",
    activity: "#activityView", office: "#officeView"
  };
  Object.values(sections).forEach((selector) => $(selector).classList.add("hidden"));
  $(sections[view] || sections.browse).classList.remove("hidden");
  $$("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#notice").classList.add("hidden");
  if (view === "browse") loadBrowse();
  if (view === "my-reports") loadMyReports();
  if (view === "my-claims") loadMyClaims();
  if (view === "office") loadOffice();
  if (view === "notifications") loadNotifications();
  if (view === "activity") loadActivity();
  refreshNotificationBadge();
}

function buildQuery(formValues) {
  const params = new URLSearchParams();
  Object.keys(formValues).forEach((key) => {
    if (formValues[key] !== undefined && formValues[key] !== null && String(formValues[key]).trim() !== "") {
      params.set(key, String(formValues[key]).trim());
    }
  });
  return params.toString();
}

function itemCard(report, options) {
  const opts = options || {};
  const icon = CATEGORY_ICONS[report.category] || "◌";
  const visual = report.image_url
    ? '<div class="item-visual"><img src="' + escapeHTML(report.image_url) + '" alt="Item photograph" loading="lazy"></div>'
    : '<div class="item-visual"><span class="visual-glyph" aria-hidden="true">' + icon + "</span></div>";
  const claimButton = opts.claim
    ? '<button class="button button-primary button-small" type="button" data-claim="' + escapeHTML(report.id) + '">Submit claim ↗</button>'
    : "";
  const characteristics = [
    report.brand ? "Brand: " + report.brand : "",
    report.primary_color ? "Colour: " + report.primary_color : "",
    report.visible_features ? report.visible_features : ""
  ].filter(Boolean);
  const characteristicBlock = characteristics.length
    ? '<div class="characteristic-list">' + characteristics.map((value) => '<span class="characteristic-chip">' + escapeHTML(value) + '</span>').join("") + '</div>'
    : "";
  const reasons = opts.reasons && opts.reasons.length
    ? '<ul class="reason-list">' + opts.reasons.map((reason) => "<li>" + escapeHTML(reason) + "</li>").join("") + "</ul>"
    : "";
  const strength = opts.strength
    ? '<span class="strength-pill strength-' + escapeHTML(opts.strength) + '">' + escapeHTML(opts.strength) + " match</span>"
    : "";
  return '<article class="item-card">' + visual +
    '<div class="item-card-body"><div class="item-topline"><span class="item-ref">' + escapeHTML(report.public_ref) + "</span>" +
    '<span class="category-pill">' + escapeHTML(report.category_label || categoryLabel(report.category)) + "</span></div>" +
    "<h3>" + escapeHTML(report.title) + "</h3>" +
    '<p class="item-description">' + escapeHTML(report.description) + "</p>" +
    characteristicBlock + reasons +
    '<div class="item-meta"><span><b>⌖</b>' + escapeHTML(report.location || "Location not specified") + "</span>" +
    '<span><b>◷</b>' + escapeHTML(humanDate(report.occurred_at)) + "</span></div>" +
    '<div class="item-actions">' + strength + claimButton + "</div></div></article>";
}

async function loadBrowse() {
  if (!currentUser) return;
  const query = buildQuery({
    q: $("#filterQuery").value,
    category: $("#filterCategory").value,
    block: $("#filterBlock").value,
    room: $("#filterRoom") ? $("#filterRoom").value : "",
    date_from: $("#filterDateFrom") ? $("#filterDateFrom").value : "",
    date_to: $("#filterDateTo") ? $("#filterDateTo").value : ""
  });
  try {
    const data = await api("/api/reports" + (query ? "?" + query : ""));
    $("#browseResults").innerHTML = data.reports.map((report) => itemCard(report, { claim: currentUser.role === "student" })).join("");
    $("#browseCount").textContent = data.reports.length + (data.reports.length === 1 ? " item" : " items");
    $("#browseEmpty").classList.toggle("hidden", data.reports.length > 0);
  } catch (error) {
    showToast(error.message, true);
  }
}

function resetSearch() {
  $("#filterQuery").value = "";
  $("#filterCategory").value = "";
  $("#filterBlock").value = "";
  if ($("#filterRoom")) $("#filterRoom").value = "";
  if ($("#filterDateFrom")) $("#filterDateFrom").value = "";
  if ($("#filterDateTo")) $("#filterDateTo").value = "";
  loadBrowse();
}

async function submitReport(event) {
  event.preventDefault();
  $("#reportError").textContent = "";
  const body = {
    report_type: $("#reportType").value,
    title: $("#reportTitle").value.trim(),
    category: $("#reportCategory").value,
    description: $("#reportDescription").value.trim(),
    brand: $("#reportBrand").value.trim() || null,
    primary_color: $("#reportColor").value.trim() || null,
    visible_features: $("#reportFeatures").value.trim() || null,
    occurred_at: $("#reportDate").value || null,
    location_block: $("#reportBlock").value || null,
    location_floor: $("#reportFloor").value || null,
    location_room: $("#reportRoom").value.trim() || null,
    location_area: $("#reportArea").value.trim() || null
  };
  const image = $("#reportImage").files[0];
  if (!body.location_block && !body.location_area) {
    $("#reportError").textContent = "Choose a campus block/building or enter a nearby area.";
    $("#reportArea").focus();
    return;
  }
  if (reportSubmitting) return;
  reportSubmitting = true;
  const submitButton = $('#reportForm button[type="submit"]');
  submitButton.disabled = true;
  try {
    const result = await api("/api/reports", { method: "POST", body });
    let successMessage = result.message;
    let photoFailed = false;
    if (image) {
      const fileBody = new FormData();
      fileBody.append("file", image);
      try {
        await api("/api/reports/" + encodeURIComponent(result.report.id) + "/image", { method: "POST", body: fileBody });
      } catch (uploadError) {
        photoFailed = true;
        successMessage += " The report was saved, but the photo upload failed: " + uploadError.message;
      }
    }
    $("#reportForm").reset();
    $("#imageLabel").textContent = "Choose a photo";
    const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
    $("#reportDate").value = now.toISOString().slice(0, 16);
    navigate("my-reports");
    showToast(successMessage, photoFailed);
  } catch (error) {
    $("#reportError").textContent = error.message;
  } finally {
    reportSubmitting = false;
    submitButton.disabled = false;
  }
}

async function loadMyReports() {
  if (!currentUser || currentUser.role !== "student") return;
  $("#matchesPanel").classList.add("hidden");
  try {
    const data = await api("/api/reports?mine=true");
    $("#myReportsList").innerHTML = data.reports.map((report) => {
      const matchButton = report.report_type === "lost" && report.status === "open"
        ? '<button class="button button-primary button-small" type="button" data-matches="' + escapeHTML(report.id) + '">Find possible matches</button>'
        : "";
      const canClose = (report.report_type === "lost" && report.status === "open" && !report.has_active_linked_claim) ||
        (report.report_type === "found" && report.status === "awaiting_intake");
      const closeButton = canClose
        ? '<button class="button button-quiet button-small" type="button" data-close-report="' + escapeHTML(report.id) +
          '" data-close-type="' + escapeHTML(report.report_type) + '">' +
          (report.report_type === "found" ? "Withdraw report" : "Close report") + '</button>'
        : "";
      const linkedClaimNote = report.report_type === "lost" && report.status === "open" && report.has_active_linked_claim
        ? '<p class="field-hint">This lost report is linked to a claim under review. Resolve the claim before closing the report.</p>'
        : "";
      const type = report.report_type === "lost" ? "Lost report" : "Found report";
      const imageNote = report.report_type === "found" && report.status === "awaiting_intake"
        ? "The office must confirm physical receipt before the item can appear in search."
        : "";
      const characteristics = [
        report.brand ? "Brand: " + report.brand : "",
        report.primary_color ? "Colour: " + report.primary_color : "",
        report.visible_features || ""
      ].filter(Boolean);
      const extra = characteristics.length
        ? '<div class="characteristic-list">' + characteristics.map((value) => '<span class="characteristic-chip">' + escapeHTML(value) + '</span>').join("") + '</div>'
        : "";
      return '<article class="list-card"><div class="list-card-head"><div><h3>' + escapeHTML(report.title) + '</h3><p>' +
        escapeHTML(type + " · " + report.public_ref) + "</p></div><span class=\"" + statusClass(report.status) + "\">" +
        escapeHTML(statusLabel(report.status)) + "</span></div><p>" + escapeHTML(report.description) + "</p>" + extra +
        '<div class="list-card-meta"><span>⌖ ' + escapeHTML(report.location) + "</span><span>◷ " + escapeHTML(humanDate(report.occurred_at)) + "</span></div>" +
        (imageNote ? '<p class="field-hint">' + escapeHTML(imageNote) + "</p>" : "") +
        linkedClaimNote +
        '<div class="card-actions">' + matchButton + closeButton + "</div></article>";
    }).join("");
    $("#myReportsEmpty").classList.toggle("hidden", data.reports.length > 0);
  } catch (error) { showToast(error.message, true); }
}

async function loadMatches(reportId) {
  selectedLostReportForMatchId = reportId;
  $("#matchesPanel").classList.remove("hidden");
  $("#matchResults").innerHTML = '<div class="list-card"><p>Comparing report details…</p></div>';
  try {
    const result = await api("/api/reports/" + encodeURIComponent(reportId) + "/matches");
    $("#matchResults").innerHTML = result.matches.map((match) => itemCard(match.report, {
      claim: true, strength: match.strength, reasons: match.reasons
    })).join("");
    if (!result.matches.length) {
      $("#matchResults").innerHTML = '<div class="empty-state"><span class="empty-icon">⌕</span><h3>No available matches yet</h3><p>Your report remains active. Try checking again after new found-item reports are received by the office.</p></div>';
    }
    $("#matchesPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { showToast(error.message, true); }
}

async function loadMyClaims() {
  if (!currentUser || currentUser.role !== "student") return;
  try {
    const data = await api("/api/claims");
    const activeCount = data.claims.filter((claim) => ["pending", "disputed", "needs_more_evidence"].includes(claim.status)).length;
    $("#claimNavCount").textContent = String(activeCount);
    $("#claimNavCount").classList.toggle("hidden", activeCount === 0);
    $("#myClaimsList").innerHTML = data.claims.map((claim) => {
      let guidance = "Your claim is awaiting review by authorised office staff.";
      if (claim.status === "disputed") guidance = claim.appeal_note
        ? "You requested a review of the earlier decision. The office must review the dispute before the claim can proceed."
        : "Competing claims exist. The item is on hold until authorised office staff resolve the competing claims.";
      if (claim.status === "needs_more_evidence") guidance = "The office has requested additional evidence. Add relevant details without sharing passwords, PINs or one-time codes.";
      if (claim.status === "approved_for_collection") guidance = "Your claim has been verified. The item is not marked returned until campus staff confirm physical handover.";
      if (claim.status === "returned") guidance = "The office recorded the return of the item. This claim is complete.";
      if (claim.status === "rejected") guidance = Number(claim.appeal_count || 0) < 1
        ? "This claim was not approved. You can request one review by explaining what evidence may have been overlooked."
        : "This claim was not approved after review. No further review request is available in this prototype; contact the campus office if needed.";
      const addEvidence = claim.status === "needs_more_evidence"
        ? '<button class="button button-primary button-small" type="button" data-add-evidence="' + escapeHTML(claim.id) + '">Add evidence</button>'
        : "";
      const disputeForm = claim.status === "rejected" && Number(claim.appeal_count || 0) < 1
        ? '<div class="claim-dispute-form"><label>Why should this decision be reviewed?<textarea data-dispute-reason="' + escapeHTML(claim.id) + '" rows="3" minlength="20" maxlength="1000" placeholder="Explain which evidence or detail should be reconsidered (at least 20 characters)."></textarea></label><button class="button button-quiet button-small" type="button" data-dispute-claim="' + escapeHTML(claim.id) + '">Request review</button></div>'
        : "";
      const appealNote = claim.appeal_note
        ? '<div class="claim-appeal-note"><strong>Your review request</strong><p>' + escapeHTML(claim.appeal_note) + '</p></div>'
        : "";
      const linkedLost = claim.linked_lost_report
        ? '<div class="linked-report-line"><strong>Linked lost report</strong><span>' +
          escapeHTML(claim.linked_lost_report.title + " · " + claim.linked_lost_report.public_ref) +
          '</span><span class="' + statusClass(claim.linked_lost_report.status) + '">' +
          escapeHTML(statusLabel(claim.linked_lost_report.status)) + '</span></div>'
        : "";
      return '<article class="list-card" data-claim-card="' + escapeHTML(claim.id) + '"><div class="list-card-head"><div><h3>' + escapeHTML(claim.report.title) + '</h3><p>' +
        escapeHTML(claim.report.public_ref + " · Submitted " + humanDate(claim.created_at)) + "</p></div><span class=\"" + statusClass(claim.status) + "\">" +
        escapeHTML(statusLabel(claim.status)) + "</span></div><p>" + escapeHTML(guidance) + '</p>' + appealNote + linkedLost + '<div class="list-card-meta"><span>⌖ ' +
        escapeHTML(claim.report.location) + "</span><span>Reference " + escapeHTML(claim.report.public_ref) + "</span></div><div class=\"card-actions\">" +
        addEvidence + "</div>" + disputeForm + "</article>";
    }).join("");
    $("#myClaimsEmpty").classList.toggle("hidden", data.claims.length > 0);
  } catch (error) { showToast(error.message, true); }
}

function openClaim(reportId) {
  const report = findReportById(reportId);
  if (!report) {
    // The report can come from a match card not currently stored in the browse response.
    loadClaimReport(reportId);
    return;
  }
  selectedClaimReport = report;
  showClaimDialog(report);
}

let lastKnownReports = [];
function findReportById(id) {
  return lastKnownReports.find((report) => report.id === id) || null;
}

async function loadClaimReport(reportId) {
  try {
    const data = await api("/api/reports?q=" + encodeURIComponent(reportId));
    const report = data.reports.find((item) => item.id === reportId);
    if (!report) throw new Error("That item is no longer available to claim. Refresh the list.");
    selectedClaimReport = report;
    showClaimDialog(report);
  } catch (error) { showToast(error.message, true); }
}

function showClaimDialog(report) {
  $("#claimError").textContent = "";
  $("#claimItemSummary").innerHTML = "<strong>" + escapeHTML(report.title) + " · " + escapeHTML(report.public_ref) +
    "</strong><small>" + escapeHTML(categoryLabel(report.category)) + " · " + escapeHTML(report.location) + "</small>";
  $("#claimEvidence").value = "";
  const preferredLostReportId = selectedLostReportForMatchId;
  selectedLostReportForMatchId = null;
  $("#claimSubmitButton").disabled = true;
  $("#claimDialog").showModal();
  loadClaimLostReports(preferredLostReportId);
}

async function loadClaimLostReports(preferredReportId) {
  const select = $("#claimLostReport");
  const requestId = ++lostReportOptionsRequest;
  select.disabled = true;
  select.innerHTML = '<option value="">Loading your open lost reports…</option>';
  try {
    const data = await api("/api/reports?mine=true&report_type=lost");
    if (requestId !== lostReportOptionsRequest) return;
    const openReports = data.reports.filter((item) => item.report_type === "lost" && item.status === "open");
    select.innerHTML = '<option value="">No linked lost report</option>' + openReports.map((item) =>
      '<option value="' + escapeHTML(item.id) + '">' + escapeHTML(item.title + " · " + item.public_ref + " · " + humanDate(item.occurred_at)) + '</option>'
    ).join("");
    if (preferredReportId && openReports.some((item) => item.id === preferredReportId)) {
      select.value = preferredReportId;
    }
    if (!openReports.length) {
      select.innerHTML = '<option value="">No open lost reports to link</option>';
    }
    select.disabled = false;
    $("#claimSubmitButton").disabled = false;
  } catch (error) {
    if (requestId !== lostReportOptionsRequest) return;
    select.innerHTML = '<option value="">Continue without linking a lost report</option>';
    select.disabled = false;
    $("#claimSubmitButton").disabled = false;
    showToast("Could not load your open lost reports. You can still submit the claim without linking one.", true);
  }
}

async function submitClaim(event) {
  event.preventDefault();
  if (!selectedClaimReport || claimSubmitting) return;
  $("#claimError").textContent = "";
  claimSubmitting = true;
  $("#claimSubmitButton").disabled = true;
  try {
    const result = await api("/api/claims", {
      method: "POST",
      body: {
        report_id: selectedClaimReport.id,
        lost_report_id: $("#claimLostReport").value || null,
        evidence: $("#claimEvidence").value.trim()
      }
    });
    $("#claimDialog").close();
    showToast(result.message + " Your evidence is private.", false);
    navigate("my-claims");
  } catch (error) {
    $("#claimError").textContent = error.message;
  } finally {
    claimSubmitting = false;
    $("#claimSubmitButton").disabled = false;
  }
}

function openAdditionalEvidence(claimId) {
  selectedEvidenceClaimId = claimId;
  const card = document.querySelector('[data-claim-card="' + CSS.escape(claimId) + '"]');
  const itemTitle = card ? card.querySelector("h3").textContent : "this item";
  $("#additionalEvidenceSummary").textContent = "Add the evidence requested for " + itemTitle + ". This response is private to you and authorised office reviewers.";
  $("#additionalEvidenceText").value = "";
  $("#additionalEvidenceError").textContent = "";
  $("#saveAdditionalEvidenceButton").disabled = false;
  $("#additionalEvidenceDialog").showModal();
}

async function submitAdditionalEvidence(event) {
  event.preventDefault();
  if (!selectedEvidenceClaimId) return;
  const evidence = $("#additionalEvidenceText").value.trim();
  if (evidence.length < 20) {
    $("#additionalEvidenceError").textContent = "Please provide at least 20 characters of relevant evidence.";
    $("#additionalEvidenceText").focus();
    return;
  }
  $("#additionalEvidenceError").textContent = "";
  $("#saveAdditionalEvidenceButton").disabled = true;
  try {
    const result = await api("/api/claims/" + encodeURIComponent(selectedEvidenceClaimId) + "/evidence", {
      method: "POST", body: { evidence }
    });
    $("#additionalEvidenceDialog").close();
    selectedEvidenceClaimId = null;
    showToast(result.claim.message, false);
    await loadMyClaims();
  } catch (error) {
    $("#additionalEvidenceError").textContent = error.message;
  } finally {
    $("#saveAdditionalEvidenceButton").disabled = false;
  }
}

async function loadOffice() {
  if (!currentUser || currentUser.role !== "office") return;
  try {
    const [summary, queueData, claimData, inventoryData] = await Promise.all([
      api("/api/office/summary"),
      api("/api/reports?report_type=found&status=awaiting_intake"),
      api("/api/claims"),
      api("/api/reports?report_type=found")
    ]);
    $("#officeStats").innerHTML = [
      ["Awaiting intake", summary.awaiting_intake],
      ["Items available", summary.available_items],
      ["Active claims", summary.active_claims],
      ["Disputed claims", summary.disputed_claims],
      ["Ready for handover", summary.approved_handover || 0],
      ["Items returned", summary.returned_items || 0]
    ].map((stat) => '<div class="stat-card"><span>' + escapeHTML(stat[0]) + '</span><strong>' + escapeHTML(stat[1]) + "</strong></div>").join("");
    const queue = queueData.reports.filter((report) => report.status === "awaiting_intake");
    $("#intakeQueue").innerHTML = queue.map((report) => intakeCard(report)).join("");
    $("#intakeEmpty").classList.toggle("hidden", queue.length > 0);
    const inventory = inventoryData.reports.filter((report) => ["available", "claim_approved"].includes(report.status) && report.tag_id);
    $("#officeInventory").innerHTML = inventory.map((report) => officeInventoryCard(report)).join("");
    $("#officeInventoryEmpty").classList.toggle("hidden", inventory.length > 0);
    const active = claimData.claims.filter((claim) => ["pending", "disputed", "needs_more_evidence"].includes(claim.status));
    $("#officeClaims").innerHTML = active.map((claim) => officeClaimCard(claim)).join("");
    $("#officeClaimsEmpty").classList.toggle("hidden", active.length > 0);
    const handovers = claimData.claims.filter((claim) => claim.status === "approved_for_collection");
    $("#handoverQueue").innerHTML = handovers.map((claim) => officeHandoverCard(claim)).join("");
    $("#handoverEmpty").classList.toggle("hidden", handovers.length > 0);
    refreshNotificationBadge();
  } catch (error) { showToast(error.message, true); }
}

function officeInventoryCard(report) {
  return '<article class="list-card"><div class="list-card-head"><div><h3>' +
    escapeHTML(report.title + " · " + report.public_ref) + '</h3><p>' +
    escapeHTML(statusLabel(report.status)) + '</p></div><span class="status-pill status-available">In campus custody</span></div>' +
    '<div class="internal-meta"><span>Physical tag: ' + escapeHTML(report.tag_id) +
    '</span><span>Stored at: ' + escapeHTML(report.storage_location || "Location needs confirmation") + '</span>' +
    '<span>Last updated: ' + escapeHTML(humanDateTime(report.updated_at)) + '</span></div>' +
    '<div class="card-actions"><button class="button button-quiet button-small" type="button" data-storage-update="' +
    escapeHTML(report.id) + '" data-current-location="' + escapeHTML(report.storage_location || "") +
    '">Update storage location</button></div></article>';
}

function officeHandoverCard(claim) {
  const report = claim.report;
  const linkedLostMeta = claim.linked_lost_report
    ? '<div class="linked-report-line office-linked-report"><strong>Linked lost report</strong><span>' +
      escapeHTML(claim.linked_lost_report.title + " · " + claim.linked_lost_report.public_ref) +
      '</span><span class="' + statusClass(claim.linked_lost_report.status) + '">' +
      escapeHTML(statusLabel(claim.linked_lost_report.status)) + '</span></div>'
    : "";
  return '<article class="list-card"><div class="list-card-head"><div><h3>' +
    escapeHTML(report.title + " · " + report.public_ref) + '</h3><p>Claimant: ' +
    escapeHTML(claim.claimant_name) + " · " + escapeHTML(claim.claimant_email) +
    "</p></div><span class=\"" + statusClass(claim.status) + "\">Verified claim</span></div>" +
    '<div class="internal-meta"><span>Physical tag: ' + escapeHTML(report.tag_id || "Not assigned") +
    "</span><span>Verification level: " + escapeHTML(report.verification_level ? "L" + report.verification_level : "Not assigned") +
    "</span><span>Stored at: " + escapeHTML(report.storage_location || "Location needs confirmation") + "</span></div>" + linkedLostMeta + "<p>Before release, compare the physical item with the tag and verify the claimant under campus policy.</p>" +
    '<div class="card-actions"><button class="button button-primary button-small" type="button" data-handover="' +
    escapeHTML(claim.id) + '" data-tag="' + escapeHTML(report.tag_id || "") + '">Confirm physical handover</button></div></article>';
}

function intakeCard(report) {
  return '<article class="list-card"><div class="list-card-head"><div><h3>' + escapeHTML(report.title) + '</h3><p>' +
    escapeHTML(report.public_ref + " · Reported " + humanDate(report.created_at)) + "</p></div><span class=\"" + statusClass(report.status) + "\">Awaiting intake</span></div>" +
    "<p>" + escapeHTML(report.description) + "</p><div class=\"list-card-meta\"><span>⌖ " + escapeHTML(report.location) +
    "</span><span>" + escapeHTML(categoryLabel(report.category)) + "</span></div>" +
    '<form class="intake-form" data-intake-form="' + escapeHTML(report.id) + '">' +
    '<label class="wide">Campus storage location<input name="storage_location" required minlength="4" maxlength="160" placeholder="Lost & Found room · cabinet A · shelf 01"></label>' +
    '<label class="wide">Private identifying detail / approved verification method<textarea name="private_detail" maxlength="1200" placeholder="Not shown to students. For restricted items, describe the authorised verification method without copying unnecessary sensitive data."></textarea></label>' +
    '<label>Estimated value band<select name="value_band"><option value="unknown">Unknown</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>' +
    '<label>Sensitivity level<select name="sensitivity_level"><option value="1">1 · Routine</option><option value="2">2 · Elevated</option><option value="3">3 · Sensitive</option><option value="4">4 · Restricted</option></select></label>' +
    '<label class="checkbox-line wide"><input type="checkbox" name="confirmed_physical_receipt" required> I confirm the physical item is in campus office custody and has been placed at the recorded storage location.</label>' +
    '<div class="wide"><button class="button button-primary button-small" type="submit">Confirm receipt, store & assign tag</button></div></form></article>';
}

function officeClaimCard(claim) {
  const report = claim.report;
  const levelNumber = Number(report.verification_level || 3);
  const level = "L" + levelNumber;
  const minimumChecks = ({ 1: 2, 2: 3, 3: 4, 4: 4 })[levelNumber] || 4;
  const privateDetail = report.private_verification_detail || "No private verification detail recorded.";
  const checks = [
    ["distinctive_features", "Distinctive features / owner-only detail match"],
    ["date_location", "Date and location are consistent"],
    ["physical_inspection", "Physical item inspected"],
    ["supporting_evidence", "Independent supporting evidence reviewed"],
    ["owner_specific_detail", "Owner-specific detail checked"],
    ["claimant_identity", "Claimant identity checked"]
  ];
  if (levelNumber >= 4) checks.push(["authorised_record", "Authorised record / custodian checked"]);
  const checklist = '<div class="verification-checklist"><div class="verification-checklist-heading"><strong>Verification checklist</strong><span>' +
    escapeHTML("Level " + levelNumber + " · minimum " + minimumChecks + " checks") +
    '</span></div><p class="field-hint">Check the evidence you actually reviewed. Claimant identity is always required; restricted items also require an authorised-record check.</p>' +
    '<div class="verification-check-grid">' + checks.map(([value, label]) =>
      '<label class="verify-check"><input type="checkbox" data-verification-check="true" value="' + escapeHTML(value) + '"><span>' + escapeHTML(label) + '</span></label>'
    ).join("") + '</div></div>';
  const actions = '<div class="decision-note"><input type="text" maxlength="800" data-note-for="' + escapeHTML(claim.id) +
    '" placeholder="Internal review note (optional)"></div><div class="card-actions">' +
    '<button class="button button-primary button-small" type="button" data-decision="approve" data-claim-id="' + escapeHTML(claim.id) + '">Verify claim</button>' +
    '<button class="button button-amber button-small" type="button" data-decision="request_more_evidence" data-claim-id="' + escapeHTML(claim.id) + '">Request evidence</button>' +
    '<button class="button button-danger button-small" type="button" data-decision="mark_disputed" data-claim-id="' + escapeHTML(claim.id) + '">Mark disputed</button>' +
    '<button class="button button-quiet button-small" type="button" data-decision="reject" data-claim-id="' + escapeHTML(claim.id) + '">Reject claim</button></div>';
  const linkedLost = claim.linked_lost_report
    ? '<div class="linked-report-line office-linked-report"><strong>Linked lost report</strong><span>' +
      escapeHTML(claim.linked_lost_report.title + " · " + claim.linked_lost_report.public_ref) +
      '</span><span class="' + statusClass(claim.linked_lost_report.status) + '">' +
      escapeHTML(statusLabel(claim.linked_lost_report.status)) + '</span></div>'
    : "";
  return '<article class="list-card" data-claim-card="' + escapeHTML(claim.id) + '"><div class="list-card-head"><div><h3>' +
    escapeHTML(report.title) + " · " + escapeHTML(report.public_ref) +
    '</h3><p>Claimant: ' + escapeHTML(claim.claimant_name) + " · " + escapeHTML(claim.claimant_email) + "</p></div><span class=\"" + statusClass(claim.status) +
    "\">" + escapeHTML(statusLabel(claim.status)) + "</span></div>" +
    '<div class="internal-meta"><span>Physical tag: ' + escapeHTML(report.tag_id || "Not assigned") + "</span><span>Verification: " + escapeHTML(level) +
    "</span><span>Value band: " + escapeHTML(report.value_band || "unknown") + "</span><span>Sensitivity: " + escapeHTML(report.sensitivity_level) + "</span></div>" +
    linkedLost +
    '<div class="claim-evidence"><strong>CLAIMANT EVIDENCE · PRIVATE</strong><p>' + escapeHTML(claim.evidence) + "</p></div>" +
    (claim.appeal_note ? '<div class="claim-appeal-note"><strong>CLAIMANT REVIEW REQUEST</strong><p>' + escapeHTML(claim.appeal_note) + '</p></div>' : "") +
    '<div class="internal-detail"><strong>INTERNAL VERIFICATION DETAIL</strong><small>' + escapeHTML(privateDetail) + "</small></div>" +
    '<div class="list-card-meta"><span>⌖ ' + escapeHTML(report.location) + "</span><span>Submitted " + escapeHTML(humanDateTime(claim.created_at)) + "</span></div>" +
    (claim.status === "disputed" ? '<p class="field-hint">' + escapeHTML(claim.appeal_note
      ? "This is a claimant-requested review of a previous rejection. Review the appeal note and evidence again."
      : "Resolve all competing active claims before approving any one claim.") + '</p>' : "") +
    checklist + actions + "</article>";
}

async function submitIntake(event) {
  event.preventDefault();
  const form = event.target;
  if (!form.matches("[data-intake-form]")) return;
  const values = new FormData(form);
  const body = {
    confirmed_physical_receipt: values.get("confirmed_physical_receipt") === "on",
    storage_location: String(values.get("storage_location") || "").trim(),
    private_detail: String(values.get("private_detail") || "").trim() || null,
    value_band: values.get("value_band"),
    sensitivity_level: Number(values.get("sensitivity_level"))
  };
  try {
    const result = await api("/api/reports/" + encodeURIComponent(form.dataset.intakeForm) + "/intake", { method: "POST", body });
    showToast("Item received, tagged and stored at " + result.report.storage_location + " · " + result.report.tag_id, false);
    loadOffice();
  } catch (error) { showToast(error.message, true); }
}



async function refreshNotificationBadge() {
  if (!currentUser) return;
  try {
    const data = await api("/api/notifications");
    const badge = $("#notificationNavCount");
    badge.textContent = String(data.unread_count || 0);
    badge.classList.toggle("hidden", !data.unread_count);
  } catch (_) {}
}

async function loadNotifications() {
  if (!currentUser) return;
  try {
    const data = await api("/api/notifications");
    $("#notificationNavCount").textContent = String(data.unread_count || 0);
    $("#notificationNavCount").classList.toggle("hidden", !data.unread_count);
    $("#notificationsList").innerHTML = data.notifications.map((item) =>
      '<article class="notification-card ' + (item.read_at ? "is-read" : "is-unread") + '">' +
      '<div class="notification-mark">' + (item.read_at ? "✓" : "•") + "</div><div class=\"notification-content\"><div class=\"notification-heading\"><strong>" +
      escapeHTML(item.title) + '</strong><span>' + escapeHTML(humanDateTime(item.created_at)) + "</span></div><p>" +
      escapeHTML(item.message) + "</p>" + (!item.read_at
        ? '<button class="button button-quiet button-small" type="button" data-notification-read="' + escapeHTML(item.id) + '">Mark read</button>'
        : "") + "</div></article>"
    ).join("");
    $("#notificationsEmpty").classList.toggle("hidden", data.notifications.length > 0);
  } catch (error) { showToast(error.message, true); }
}

async function markNotificationRead(notificationId) {
  try {
    await api("/api/notifications/" + encodeURIComponent(notificationId) + "/read", { method: "POST" });
    await loadNotifications();
  } catch (error) { showToast(error.message, true); }
}

async function markAllNotificationsRead() {
  try {
    await api("/api/notifications/read-all", { method: "POST" });
    await loadNotifications();
    showToast("Notifications marked as read.", false);
  } catch (error) { showToast(error.message, true); }
}

async function loadActivity() {
  if (!currentUser || currentUser.role !== "student") return;
  try {
    const data = await api("/api/activity/me");
    const total = Number(data.total_points || 0);
    const next = data.next_milestone;
    const progress = next ? Math.min(100, total / next.threshold * 100) : 100;
    const nextText = next
      ? (data.points_to_next_milestone + " more points to " + next.tier)
      : "All current recognition milestones earned";
    $("#activityOverview").innerHTML =
      '<div class="activity-points-card"><div><p class="eyebrow">VERIFIED ACTIVITY</p><strong>' + escapeHTML(total) +
      '</strong><span>total points</span></div><div class="points-symbol">✦</div><p class="muted">Points are awarded for contributions verified by the campus office.</p></div>' +
      '<div class="milestone-card"><div class="milestone-heading"><div><p class="eyebrow">NEXT MILESTONE</p><h3>' +
      escapeHTML(next ? next.tier : "Recognition complete") + '</h3></div><span class="count-pill">' +
      escapeHTML(next ? (next.threshold + " pts") : "Complete") + "</span></div><div class=\"progress-track\"><span style=\"width:" +
      progress + '%"></span></div><p class="muted">' + escapeHTML(nextText) + '</p><div class="point-rules"><span>+' +
      escapeHTML(data.rules.verified_intake) + ' <small>verified office intake</small></span><span>+' +
      escapeHTML(data.rules.verified_return) + ' <small>verified return</small></span></div></div>';
    const leaderboard = await api("/api/leaderboard");
    $("#leaderboardParticipantCount").textContent = leaderboard.participant_count + (leaderboard.participant_count === 1 ? " contributor" : " contributors");
    $("#leaderboardSummary").innerHTML = leaderboard.my_rank
      ? '<div class="leaderboard-self"><span>Your current rank</span><strong>#' + escapeHTML(leaderboard.my_rank) + '</strong><small>' + escapeHTML(leaderboard.my_total_points) + ' verified points</small></div>'
      : '<div class="leaderboard-self"><span>Your current rank</span><strong>—</strong><small>Earn points when the office verifies a contribution.</small></div>';
    $("#leaderboardList").innerHTML = leaderboard.leaders.map((leader) =>
      '<div class="leaderboard-row ' + (leader.is_me ? "leaderboard-row-self" : "") + '"><span class="leaderboard-rank">#' +
      escapeHTML(leader.rank) + '</span><span class="leaderboard-name">' + escapeHTML(leader.display_name) + '</span><span class="leaderboard-detail">' +
      escapeHTML(leader.verified_reports) + ' reports</span><strong class="leaderboard-points">' + escapeHTML(leader.total_points) + ' pts</strong></div>'
    ).join("");
    $("#leaderboardEmpty").classList.toggle("hidden", leaderboard.leaders.length > 0);
    $("#certificateList").innerHTML = data.certificates.map((certificate) =>
      '<article class="certificate-card"><div class="certificate-emblem">✧</div><div class="certificate-copy"><span class="item-ref">' +
      escapeHTML(certificate.serial) + "</span><h3>" + escapeHTML(certificate.tier) + '</h3><p class="muted">' +
      escapeHTML(certificate.points_at_issue + " points at issue · " + humanDate(certificate.issued_at)) + '</p></div><button class="button button-primary button-small" type="button" data-certificate-download="' +
      escapeHTML(certificate.id) + '">Download PDF ↗</button></article>'
    ).join("");
    $("#certificateEmpty").classList.toggle("hidden", data.certificates.length > 0);
    $("#activityLedger").innerHTML = data.ledger.map((entry) =>
      '<article class="ledger-row"><div class="ledger-icon">＋</div><div class="ledger-copy"><strong>' +
      escapeHTML(entry.reason) + '</strong><small>' + escapeHTML(humanDateTime(entry.created_at)) +
      (entry.report_id ? " · Verified report recorded" : "") + '</small></div><span class="ledger-points">+' +
      escapeHTML(entry.points) + " pts</span></article>"
    ).join("");
    $("#activityEmpty").classList.toggle("hidden", data.ledger.length > 0);
  } catch (error) { showToast(error.message, true); }
}

function openStorageUpdate(reportId, currentLocation, itemTitle) {
  selectedStorageReportId = reportId;
  $("#storageUpdateSummary").textContent = itemTitle + ". Update this record only after the item has physically been moved.";
  $("#storageUpdateLocation").value = currentLocation || "";
  $("#storageUpdateNote").value = "";
  $("#storageUpdateError").textContent = "";
  $("#saveStorageUpdateButton").disabled = false;
  $("#storageUpdateDialog").showModal();
}

async function submitStorageLocation(event) {
  event.preventDefault();
  if (!selectedStorageReportId) return;
  const storageLocation = $("#storageUpdateLocation").value.trim();
  if (storageLocation.length < 4) {
    $("#storageUpdateError").textContent = "Enter a specific room, cabinet, shelf or storage area.";
    $("#storageUpdateLocation").focus();
    return;
  }
  $("#storageUpdateError").textContent = "";
  $("#saveStorageUpdateButton").disabled = true;
  try {
    const result = await api("/api/reports/" + encodeURIComponent(selectedStorageReportId) + "/storage", {
      method: "POST",
      body: {
        storage_location: storageLocation,
        note: $("#storageUpdateNote").value.trim() || null
      }
    });
    $("#storageUpdateDialog").close();
    selectedStorageReportId = null;
    showToast(result.message, false);
    await loadOffice();
  } catch (error) {
    $("#storageUpdateError").textContent = error.message;
  } finally {
    $("#saveStorageUpdateButton").disabled = false;
  }
}

async function openCloseReport(reportId, reportType) {
  selectedCloseReportId = reportId;
  selectedCloseReportType = reportType;
  $("#closeReportError").textContent = "";
  $("#closeReportNote").value = "";
  const isFound = reportType === "found";
  $("#closeReportDialogTitle").textContent = isFound ? "Withdraw found report" : "Close lost report";
  $("#closeReportDescription").textContent = isFound
    ? "Withdraw this report only if you have not yet handed the physical item to the campus office. Once staff accept it and assign a tag, contact the office instead."
    : "Close your search if you recovered the item elsewhere, no longer need to search, or submitted a duplicate. Closed reports stop generating match suggestions.";
  $("#confirmCloseReportButton").textContent = isFound ? "Withdraw report" : "Close report";
  $("#closeReportReason").innerHTML = isFound
    ? '<option value="found_report_withdrawn">I cannot deliver the item to the office</option>'
    : '<option value="recovered_elsewhere">I recovered the item elsewhere</option><option value="no_longer_searching">I no longer need to search</option><option value="duplicate">This is a duplicate report</option>';
  $("#closeReportReason").value = isFound ? "found_report_withdrawn" : "no_longer_searching";
  $("#closeReportDialog").showModal();
}

async function submitCloseReport(event) {
  event.preventDefault();
  if (!selectedCloseReportId) return;
  try {
    const result = await api("/api/reports/" + encodeURIComponent(selectedCloseReportId) + "/close", {
      method: "POST",
      body: { reason: $("#closeReportReason").value, note: $("#closeReportNote").value.trim() || null }
    });
    $("#closeReportDialog").close();
    selectedCloseReportId = null;
    selectedCloseReportType = null;
    showToast(result.message, false);
    await loadMyReports();
  } catch (error) { $("#closeReportError").textContent = error.message; }
}

async function submitClaimDispute(claimId) {
  const textarea = $('[data-dispute-reason="' + CSS.escape(claimId) + '"]');
  const reason = textarea ? textarea.value.trim() : "";
  if (reason.length < 20) {
    showToast("Please explain why the decision should be reviewed (at least 20 characters).", true);
    if (textarea) textarea.focus();
    return;
  }
  try {
    const result = await api("/api/claims/" + encodeURIComponent(claimId) + "/dispute", {
      method: "POST", body: { reason }
    });
    showToast(result.message, false);
    await loadMyClaims();
  } catch (error) { showToast(error.message, true); }
}

function openHandoverDialog(claimId, itemTitle) {
  selectedHandoverClaimId = claimId;
  $("#handoverSummary").textContent = "Before releasing " + itemTitle + ", read the physical label and compare it with the Tag ID in the office record.";
  $("#handoverTag").value = "";
  $("#handoverIdentityChecked").checked = false;
  $("#handoverPhysicalChecked").checked = false;
  $("#handoverNote").value = "";
  $("#handoverError").textContent = "";
  $("#confirmHandoverButton").disabled = false;
  $("#handoverDialog").showModal();
  $("#handoverTag").focus();
}

async function submitHandover(event) {
  event.preventDefault();
  if (!selectedHandoverClaimId) return;
  const tagId = $("#handoverTag").value.trim();
  if (tagId.length < 4) {
    $("#handoverError").textContent = "Enter the exact physical Tag ID from the item label.";
    $("#handoverTag").focus();
    return;
  }
  if (!$("#handoverIdentityChecked").checked || !$("#handoverPhysicalChecked").checked) {
    $("#handoverError").textContent = "Confirm both the identity check and actual physical handover.";
    return;
  }
  $("#handoverError").textContent = "";
  $("#confirmHandoverButton").disabled = true;
  try {
    const result = await api("/api/claims/" + encodeURIComponent(selectedHandoverClaimId) + "/handover", {
      method: "POST",
      body: {
        tag_id: tagId,
        confirmed_physical_handover: $("#handoverPhysicalChecked").checked,
        claimant_identity_checked: $("#handoverIdentityChecked").checked,
        note: $("#handoverNote").value.trim() || null
      }
    });
    $("#handoverDialog").close();
    selectedHandoverClaimId = null;
    showToast(result.message, false);
    await loadOffice();
  } catch (error) {
    $("#handoverError").textContent = error.message;
  } finally {
    $("#confirmHandoverButton").disabled = false;
  }
}


async function submitDecision(claimId, action) {
  const noteInput = $('[data-note-for="' + CSS.escape(claimId) + '"]');
  const note = noteInput ? noteInput.value.trim() : "";
  const card = $('[data-claim-card="' + CSS.escape(claimId) + '"]');
  const verificationChecks = action === "approve" && card
    ? $('[data-verification-check]:checked', card).map((input) => input.value)
    : [];
  const prompts = {
    approve: "Verify this claim only after reviewing the private evidence and checking the required verification items. It will then move to the handover queue.",
    reject: "Reject this claim after reviewing the evidence?",
    request_more_evidence: "Ask the claimant for additional evidence?",
    mark_disputed: "Keep this claim on hold as disputed?"
  };
  if (!window.confirm(prompts[action] || "Update claim review?")) return;
  try {
    const result = await api("/api/claims/" + encodeURIComponent(claimId) + "/decision", {
      method: "POST", body: { action: action, note: note || null, verification_checks: verificationChecks }
    });
    showToast(result.message, false);
    loadOffice();
  } catch (error) { showToast(error.message, true); }
}

async function start() {
  try {
    await loadConfig();
  } catch (error) {
    $("#loginError").textContent = "Could not load configuration: " + error.message;
    return;
  }
  try {
    const data = await api("/api/me");
    enterApp(data.user);
  } catch (_) {
    showLogin();
  }
}

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#loginError").textContent = "";
  try {
    const result = await api("/api/login", {
      method: "POST",
      body: { email: $("#loginEmail").value.trim(), password: $("#loginPassword").value }
    });
    enterApp(result.user);
    showToast("Signed in successfully.", false);
  } catch (error) { $("#loginError").textContent = error.message; }
});

$("#fillStudent").addEventListener("click", () => {
  $("#loginEmail").value = "student@lostlink.local";
  $("#loginPassword").value = "student123";
});
$("#fillOffice").addEventListener("click", () => {
  $("#loginEmail").value = "office@lostlink.local";
  $("#loginPassword").value = "office123";
});
$("#logoutButton").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST" }); } catch (_) {}
  showLogin();
});
$("#studentNav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (button) navigate(button.dataset.view);
});
document.addEventListener("click", (event) => {
  const go = event.target.closest("[data-go]");
  if (go) navigate(go.dataset.go);
  const matches = event.target.closest("[data-matches]");
  if (matches) loadMatches(matches.dataset.matches);
  const evidence = event.target.closest("[data-add-evidence]");
  if (evidence) openAdditionalEvidence(evidence.dataset.addEvidence);
  const dispute = event.target.closest("[data-dispute-claim]");
  if (dispute) submitClaimDispute(dispute.dataset.disputeClaim);
  const closeReport = event.target.closest("[data-close-report]");
  if (closeReport) openCloseReport(closeReport.dataset.closeReport, closeReport.dataset.closeType);
  const decision = event.target.closest("[data-decision]");
  if (decision) submitDecision(decision.dataset.claimId, decision.dataset.decision);
  const handover = event.target.closest("[data-handover]");
  if (handover) {
    const itemTitle = handover.closest(".list-card")?.querySelector("h3")?.textContent || "this item";
    openHandoverDialog(handover.dataset.handover, itemTitle);
  }
  const storageUpdate = event.target.closest("[data-storage-update]");
  if (storageUpdate) {
    const itemTitle = storageUpdate.closest(".list-card")?.querySelector("h3")?.textContent || "Tagged item";
    openStorageUpdate(storageUpdate.dataset.storageUpdate, storageUpdate.dataset.currentLocation, itemTitle);
  }
  const notification = event.target.closest("[data-notification-read]");
  if (notification) markNotificationRead(notification.dataset.notificationRead);
  const certificate = event.target.closest("[data-certificate-download]");
  if (certificate) window.location.href = "/api/certificates/" + encodeURIComponent(certificate.dataset.certificateDownload) + "/download";
});
$("#searchForm").addEventListener("submit", (event) => { event.preventDefault(); loadBrowse(); });
$("#readAllNotifications").addEventListener("click", markAllNotificationsRead);
$("#clearFilters").addEventListener("click", resetSearch);
$("#reportForm").addEventListener("submit", submitReport);
$("#reportImage").addEventListener("change", () => {
  const file = $("#reportImage").files[0];
  $("#imageLabel").textContent = file ? file.name : "Choose a photo";
});
$("#cancelReport").addEventListener("click", () => navigate("browse"));
$("#claimForm").addEventListener("submit", submitClaim);
$("#handoverForm").addEventListener("submit", submitHandover);
$("#closeHandover").addEventListener("click", () => { $("#handoverDialog").close(); selectedHandoverClaimId = null; });
$("#cancelHandover").addEventListener("click", () => { $("#handoverDialog").close(); selectedHandoverClaimId = null; });
$("#additionalEvidenceForm").addEventListener("submit", submitAdditionalEvidence);
$("#closeAdditionalEvidence").addEventListener("click", () => { $("#additionalEvidenceDialog").close(); selectedEvidenceClaimId = null; });
$("#cancelAdditionalEvidence").addEventListener("click", () => { $("#additionalEvidenceDialog").close(); selectedEvidenceClaimId = null; });
$("#storageUpdateForm").addEventListener("submit", submitStorageLocation);
$("#closeStorageUpdate").addEventListener("click", () => { $("#storageUpdateDialog").close(); selectedStorageReportId = null; });
$("#cancelStorageUpdate").addEventListener("click", () => { $("#storageUpdateDialog").close(); selectedStorageReportId = null; });
$("#closeReportForm").addEventListener("submit", submitCloseReport);
$("#closeCloseReport").addEventListener("click", () => { $("#closeReportDialog").close(); selectedCloseReportId = null; selectedCloseReportType = null; });
$("#cancelCloseReport").addEventListener("click", () => { $("#closeReportDialog").close(); selectedCloseReportId = null; selectedCloseReportType = null; });
$("#closeClaim").addEventListener("click", () => $("#claimDialog").close());
$("#cancelClaim").addEventListener("click", () => $("#claimDialog").close());
$("#closeMatches").addEventListener("click", () => $("#matchesPanel").classList.add("hidden"));
$("#appView").addEventListener("submit", submitIntake);
$("#browseResults").addEventListener("click", (event) => {
  const button = event.target.closest("[data-claim]");
  if (!button) return;
  const card = button.closest(".item-card");
  const ref = card.querySelector(".item-ref").textContent;
  // Keep the current browse records available to the claim dialog without exposing internal fields.
  const query = $("#filterQuery").value;
  loadReportForClaimByRef(button.dataset.claim, ref, query);
});
$("#matchResults").addEventListener("click", (event) => {
  const button = event.target.closest("[data-claim]");
  if (button) loadReportForClaimByRef(button.dataset.claim, button.closest(".item-card").querySelector(".item-ref").textContent, "");
});

async function loadReportForClaimByRef(reportId, publicRef, searchQuery) {
  try {
    const data = await api("/api/reports?" + buildQuery({ q: searchQuery || publicRef }));
    const report = data.reports.find((item) => item.id === reportId);
    if (report) {
      selectedClaimReport = report;
      showClaimDialog(report);
      return;
    }
    // A report from the match list may not match the current text filter.
    const retry = await api("/api/reports?q=" + encodeURIComponent(publicRef));
    const found = retry.reports.find((item) => item.id === reportId);
    if (!found) throw new Error("This item is no longer available to claim. Refresh the list.");
    selectedClaimReport = found;
    showClaimDialog(found);
  } catch (error) { showToast(error.message, true); }
}

start();
