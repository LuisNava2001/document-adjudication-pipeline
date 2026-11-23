/* Static viewer for the adjudication demo.
 *
 * No framework and no network access: every value comes from data.js, which
 * scripts/build_demo_data.py generates from a deterministic pipeline run.
 * All data is inserted with textContent, never parsed as HTML.
 */
(function () {
  "use strict";

  const DATA = window.ADJUDICATION_DEMO;

  const ICON = {
    check: "✓",
    cross: "✕",
    bang: "!",
    retry: "↻",
    ban: "⊘",
    dash: "–",
    question: "?",
    list: "≡",
  };

  const CASE_OUTCOMES = {
    APPROVED: { label: "Approved", tone: "good", icon: ICON.check },
    REJECTED: { label: "Rejected", tone: "critical", icon: ICON.cross },
    MANUAL_REVIEW: { label: "Manual review", tone: "warning", icon: ICON.bang },
    FAILED: { label: "Processing failed", tone: "serious", icon: ICON.retry },
    INVALID_INPUT: { label: "Invalid input", tone: "neutral", icon: ICON.ban },
  };

  const RULE_OUTCOMES = {
    PASS: { label: "Pass", tone: "good", icon: ICON.check },
    FAIL: { label: "Fail", tone: "critical", icon: ICON.cross },
    SKIPPED: { label: "Skipped", tone: "warning", icon: ICON.question },
    NOT_APPLICABLE: { label: "Not applicable", tone: "neutral", icon: ICON.dash },
  };

  const FIELD_LABELS = {
    merchant_name: "Merchant",
    receipt_number: "Receipt no.",
    transaction_date: "Date",
    currency: "Currency",
    tax: "Tax",
    total_amount: "Total",
  };

  const state = { filter: "ALL", selected: null, onlyIssues: false };
  const ruleTitles = new Map();

  // ---- DOM helpers -------------------------------------------------------

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : String(value));
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function badge(meta, extraClass) {
    return el(
      "span",
      { class: `badge tone-${meta.tone}${extraClass ? " " + extraClass : ""}` },
      el("span", { class: "badge-icon", "aria-hidden": "true", text: meta.icon }),
      el("span", { class: "badge-label", text: meta.label })
    );
  }

  function formatValue(value) {
    if (value === null || value === undefined) return "null";
    if (Array.isArray(value)) return value.length ? value.map(formatValue).join(", ") : "(none)";
    if (typeof value === "object") {
      return Object.entries(value).map(([k, v]) => `${k}: ${formatValue(v)}`).join("; ");
    }
    return String(value);
  }

  function keyValues(entries, extraClass) {
    const list = el("dl", { class: `kv${extraClass ? " " + extraClass : ""}` });
    for (const [label, value] of entries) {
      list.append(el("dt", { text: label }), el("dd", { text: formatValue(value) }));
    }
    return list;
  }

  function countBy(items, keyFn) {
    const counts = {};
    for (const item of items) counts[keyFn(item)] = (counts[keyFn(item)] || 0) + 1;
    return counts;
  }

  // ---- case selection ----------------------------------------------------

  function caseOutcome(item) {
    return item.result.decision ? item.result.decision.outcome : item.result.status;
  }

  function visibleCases() {
    return DATA.cases.filter((item) => state.filter === "ALL" || caseOutcome(item) === state.filter);
  }

  function currentHash() {
    return decodeURIComponent(window.location.hash.slice(1));
  }

  function open(key) {
    if (currentHash() !== key) window.location.hash = encodeURIComponent(key);
    else show(key);
    if (window.matchMedia("(max-width: 900px)").matches) {
      document.getElementById("detail").scrollIntoView({ block: "start" });
    }
  }

  function show(key) {
    const item = DATA.cases.find((c) => c.key === key) || DATA.cases[0];
    state.selected = item.key;
    document.title = `${item.key} - Adjudication Demo Viewer`;
    for (const button of document.querySelectorAll(".case")) {
      if (button.dataset.key === item.key) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    }
    renderDetail(item);
  }

  // ---- side panel --------------------------------------------------------

  function renderFilters() {
    const host = document.getElementById("filters");
    const counts = countBy(DATA.cases, caseOutcome);
    const options = [["ALL", { label: "All claims", tone: "accent", icon: null }]];
    for (const [key, meta] of Object.entries(CASE_OUTCOMES)) if (counts[key]) options.push([key, meta]);
    host.replaceChildren(
      ...options.map(([key, meta]) =>
        el(
          "button",
          {
            type: "button",
            class: `chip tone-${meta.tone}`,
            "aria-pressed": String(state.filter === key),
            onclick: () => {
              state.filter = key;
              renderFilters();
              renderList();
            },
          },
          meta.icon ? el("span", { class: "chip-icon", "aria-hidden": "true", text: meta.icon }) : null,
          el("span", { class: "chip-value", text: String(key === "ALL" ? DATA.cases.length : counts[key]) }),
          el("span", { class: "chip-label", text: meta.label })
        )
      )
    );
  }

  function renderList() {
    const list = document.getElementById("case-list");
    list.replaceChildren(
      ...visibleCases().map((item) =>
        el(
          "li",
          null,
          el(
            "button",
            {
              type: "button",
              class: "case",
              "data-key": item.key,
              "aria-current": item.key === state.selected ? "true" : null,
              onclick: () => open(item.key),
            },
            el("span", { class: "case-id", text: item.key }),
            badge(CASE_OUTCOMES[caseOutcome(item)]),
            el("span", { class: "case-scenario", text: item.scenario || "" })
          )
        )
      )
    );
  }

  // ---- detail ------------------------------------------------------------

  function renderDetail(item) {
    document.getElementById("detail").replaceChildren(
      detailHeader(item),
      stageStrip(item),
      decisionBasis(item),
      el("div", { class: "grid-2" }, claimCard(item), processingCard(item)),
      documentsSection(item),
      rulesSection(item),
      auditSection(item),
      rawSection(item)
    );
  }

  function summaryText(result) {
    if (result.decision) return result.decision.summary;
    if (result.status === "FAILED") return "No decision: a retryable dependency failed. The claim can be resubmitted.";
    return "No decision: the submission could not be parsed into a claim.";
  }

  function detailHeader(item) {
    return el(
      "header",
      { class: "detail-head" },
      el("div", { class: "detail-title" }, el("h2", { text: item.key }), badge(CASE_OUTCOMES[caseOutcome(item)], "badge-lg")),
      item.scenario ? el("p", { class: "scenario", text: item.scenario }) : null,
      el("p", { class: "summary", text: summaryText(item.result) }),
      item.note ? el("p", { class: "note", text: item.note }) : null
    );
  }

  function stageStrip(item) {
    const r = item.result;
    const events = r.audit_trail;
    const accepted = events.some((e) => e.stage === "INGESTION" && e.event === "ACCEPTED");
    const stages = [];

    stages.push(
      accepted
        ? ["Ingestion", "good", ICON.check, "Accepted"]
        : ["Ingestion", "critical", ICON.cross, `Rejected: ${r.errors.length} error(s)`]
    );

    const documentCount = r.extractions.length + r.extraction_failures.length;
    if (!accepted) stages.push(["Extraction", "neutral", ICON.dash, "Not run"]);
    else if (documentCount === 0) stages.push(["Extraction", "neutral", ICON.dash, "No documents"]);
    else {
      const retryable = r.extraction_failures.some((f) => f.retryable);
      const permanent = r.extraction_failures.some((f) => !f.retryable);
      const retries = events.filter((e) => e.event === "ATTEMPT_FAILED").length;
      let text = `${r.extractions.length}/${documentCount} extracted`;
      if (retries) text += `, ${retries} ${retries === 1 ? "retry" : "retries"}`;
      stages.push([
        "Extraction",
        retryable ? "serious" : permanent ? "warning" : "good",
        retryable ? ICON.retry : permanent ? ICON.bang : ICON.check,
        text,
      ]);
    }

    if (!r.rule_results.length) stages.push(["Validation", "neutral", ICON.dash, "Not run"]);
    else {
      const n = countBy(r.rule_results, (x) => x.outcome);
      const blocking = r.rule_results.some((x) => x.outcome === "FAIL" && x.severity === "REJECT");
      const doubtful = n.FAIL || n.SKIPPED;
      stages.push([
        "Validation",
        blocking ? "critical" : doubtful ? "warning" : "good",
        blocking ? ICON.cross : doubtful ? ICON.bang : ICON.check,
        `${n.PASS || 0} pass, ${n.FAIL || 0} fail, ${n.SKIPPED || 0} skipped`,
      ]);
    }

    if (r.decision) {
      const meta = CASE_OUTCOMES[r.decision.outcome];
      stages.push(["Decision", meta.tone, meta.icon, meta.label]);
    } else stages.push(["Decision", "neutral", ICON.dash, "No decision"]);

    stages.push(["Audit", "accent", ICON.list, `${events.length} events`]);

    return el(
      "ol",
      { class: "stages", "aria-label": "Pipeline stages" },
      stages.map(([name, tone, icon, text]) =>
        el(
          "li",
          { class: `stage tone-${tone}` },
          el("span", { class: "stage-icon", "aria-hidden": "true", text: icon }),
          el("span", { class: "stage-body" }, el("span", { class: "stage-name", text: name }), el("span", { class: "stage-text", text }))
        )
      )
    );
  }

  function decisionBasis(item) {
    const r = item.result;
    const section = el("section", { class: "card" }, el("h3", { text: "Decision basis" }));
    if (r.decision && r.decision.reasons.length) {
      section.append(el("ul", { class: "reasons" }, r.decision.reasons.map(reasonItem)));
    } else if (r.decision) {
      section.append(
        el("p", { text: `${r.decision.summary} No check failed and none lacked evidence, so the claim was approved on positive evidence.` })
      );
    }
    if (r.errors.length) section.append(el("ul", { class: "errors" }, r.errors.map((error) => el("li", { text: error }))));
    return section;
  }

  function reasonItem(result) {
    const meta = RULE_OUTCOMES[result.outcome];
    return el(
      "li",
      { class: `reason tone-${meta.tone}` },
      el(
        "div",
        { class: "reason-head" },
        badge(meta),
        el("span", { class: "rule-id", text: result.rule_id }),
        el("span", { class: "rule-title", text: ruleTitles.get(result.rule_id) || "" }),
        el("span", { class: "tag", text: result.severity }),
        el("span", { class: "tag", text: result.document_id || "claim" })
      ),
      el("p", { class: "reason-message", text: result.message }),
      Object.keys(result.evidence).length ? keyValues(Object.entries(result.evidence), "compact") : null
    );
  }

  function claimCard(item) {
    const claim = item.claim && typeof item.claim === "object" ? item.claim : {};
    const documents = Array.isArray(claim.documents) ? claim.documents.length : "-";
    return el(
      "section",
      { class: "card" },
      el("h3", { text: "Claim submission" }),
      keyValues([
        ["Claim", claim.claim_id],
        ["Claimant", claim.claimant_id],
        ["Category", claim.category],
        ["Claimed", `${claim.claimed_amount} ${claim.currency}`],
        ["Submitted", claim.submitted_on],
        ["Description", claim.description],
        ["Documents", documents],
      ])
    );
  }

  function processingCard(item) {
    const r = item.result;
    return el(
      "section",
      { class: "card" },
      el("h3", { text: "Processing" }),
      keyValues([
        ["Status", r.status],
        ["Trace id", r.trace_id],
        ["Source", r.source],
        ["Input digest", r.input_digest],
        ["Policy", `${r.policy_version} (${r.policy_digest.slice(0, 12)})`],
        ["Schema", r.schema_version],
      ])
    );
  }

  function documentsSection(item) {
    const documents = item.claim && Array.isArray(item.claim.documents) ? item.claim.documents : [];
    const section = el("section", { class: "card" }, el("h3", { text: `Documents (${documents.length})` }));
    if (!documents.length) {
      section.append(el("p", { class: "muted", text: "No supporting document attached." }));
      return section;
    }
    for (const ref of documents) section.append(documentBlock(item, ref));
    return section;
  }

  function documentBlock(item, ref) {
    const id = ref.document_id;
    const extraction = item.result.extractions.find((e) => e.document_id === id);
    const failure = item.result.extraction_failures.find((f) => f.document_id === id);
    let status;
    if (extraction) status = badge({ label: `Extracted on attempt ${extraction.attempts}`, tone: "good", icon: ICON.check });
    else if (failure) {
      status = badge({
        label: `${failure.kind}${failure.retryable ? ", retryable" : ""}`,
        tone: failure.retryable ? "serious" : "warning",
        icon: failure.retryable ? ICON.retry : ICON.bang,
      });
    } else status = badge({ label: "Not processed", tone: "neutral", icon: ICON.dash });

    const text = item.documents[id];
    return el(
      "article",
      { class: "document" },
      el("div", { class: "document-head" }, el("h4", { text: id }), status),
      el(
        "div",
        { class: "document-body" },
        el(
          "figure",
          { class: "receipt" },
          el("figcaption", { text: "Synthetic source document" }),
          text ? el("pre", { text }) : el("p", { class: "muted", text: "Source text unavailable." })
        ),
        el(
          "div",
          { class: "extraction" },
          el("p", { class: "caption", text: "Recorded extraction result (simulated, no OCR)" }),
          extraction ? fieldsTable(extraction) : failureBox(failure),
          extraction && extraction.line_items.length ? lineItemsTable(extraction) : null
        )
      )
    );
  }

  function meter(value, threshold, low) {
    const fill = el("span", { class: "meter-fill" });
    fill.style.width = `${Math.round(value * 100)}%`;
    const tick = el("span", { class: "meter-threshold" });
    tick.style.left = `${threshold * 100}%`;
    return el(
      "span",
      { class: "meter-wrap" },
      el("span", { class: "meter", role: "img", "aria-label": `confidence ${value.toFixed(2)}, threshold ${threshold.toFixed(2)}` }, fill, tick),
      el("span", { class: "meter-value", text: value.toFixed(2) }),
      low
        ? el("span", { class: "flag" }, el("span", { class: "flag-icon", "aria-hidden": "true", text: "!" }), el("span", { text: "below threshold" }))
        : null
    );
  }

  function fieldsTable(extraction) {
    const threshold = DATA.policy.min_field_confidence;
    const required = new Set(DATA.policy.required_fields);
    const rows = Object.entries(extraction.fields).map(([name, field]) => {
      const low = required.has(name) && field.value !== null && field.confidence < threshold;
      return el(
        "tr",
        { class: low ? "low" : null },
        el(
          "th",
          { scope: "row" },
          el("span", { text: FIELD_LABELS[name] || name }),
          required.has(name) ? el("span", { class: "req", title: "required field", text: "*" }) : null
        ),
        el("td", { class: "value", text: field.value === null ? "-" : field.value }),
        el("td", null, meter(field.confidence, threshold, low))
      );
    });
    return el(
      "div",
      { class: "table-wrap" },
      el(
        "table",
        { class: "fields" },
        el("thead", null, el("tr", null, ["Field", "Value", "Confidence"].map((t) => el("th", { scope: "col", text: t })))),
        el("tbody", null, rows)
      ),
      el("p", { class: "muted small", text: `* required by policy. Tick marks the ${threshold.toFixed(2)} confidence threshold.` })
    );
  }

  function lineItemsTable(extraction) {
    return el(
      "div",
      { class: "table-wrap items" },
      el(
        "table",
        null,
        el("thead", null, el("tr", null, ["Line item", "Amount", "Confidence"].map((t) => el("th", { scope: "col", text: t })))),
        el(
          "tbody",
          null,
          extraction.line_items.map((line) =>
            el(
              "tr",
              null,
              el("td", { text: line.description }),
              el("td", { class: "num", text: line.amount === null ? "-" : line.amount }),
              el("td", { class: "num", text: line.confidence.toFixed(2) })
            )
          )
        )
      )
    );
  }

  function failureBox(failure) {
    if (!failure) return el("p", { class: "muted", text: "No extraction outcome recorded." });
    return el(
      "div",
      { class: `callout tone-${failure.retryable ? "serious" : "warning"}` },
      keyValues([
        ["Failure", failure.kind],
        ["Retryable", failure.retryable ? "yes" : "no"],
        ["Attempts", failure.attempts],
        ["Message", failure.message],
      ])
    );
  }

  function rulesSection(item) {
    const results = item.result.rule_results;
    const section = el("section", { class: "card" });
    const head = el("div", { class: "section-head" }, el("h3", { text: `Rule results (${results.length})` }));
    section.append(head);
    if (!results.length) {
      section.append(el("p", { class: "muted", text: "Validation did not run for this submission." }));
      return section;
    }
    const tbody = el("tbody");
    head.append(
      el(
        "label",
        { class: "toggle" },
        el("input", {
          type: "checkbox",
          checked: state.onlyIssues,
          onchange: (event) => {
            state.onlyIssues = event.target.checked;
            fillRuleRows(tbody, results);
          },
        }),
        el("span", { text: "Only checks that did not pass" })
      )
    );
    fillRuleRows(tbody, results);
    section.append(
      el(
        "div",
        { class: "table-wrap" },
        el(
          "table",
          { class: "rules" },
          el(
            "thead",
            null,
            el("tr", null, ["Rule", "Check", "Scope", "Outcome", "Explanation and evidence"].map((t) => el("th", { scope: "col", text: t })))
          ),
          tbody
        )
      )
    );
    return section;
  }

  function fillRuleRows(tbody, results) {
    const shown = results.filter((r) => !state.onlyIssues || r.outcome === "FAIL" || r.outcome === "SKIPPED");
    if (!shown.length) {
      tbody.replaceChildren(el("tr", null, el("td", { colspan: "5", class: "muted", text: "Every check passed or did not apply." })));
      return;
    }
    tbody.replaceChildren(
      ...shown.map((r) =>
        el(
          "tr",
          { class: `outcome-${r.outcome.toLowerCase()}` },
          el("td", { class: "mono", text: r.rule_id }),
          el("td", { text: ruleTitles.get(r.rule_id) || "" }),
          el("td", { class: "mono", text: r.document_id || "claim" }),
          el("td", null, badge(RULE_OUTCOMES[r.outcome])),
          el(
            "td",
            null,
            el("span", { text: r.message }),
            Object.keys(r.evidence).length
              ? el("details", null, el("summary", { text: "Evidence" }), keyValues(Object.entries(r.evidence), "compact"))
              : null
          )
        )
      )
    );
  }

  function auditSection(item) {
    const r = item.result;
    return el(
      "section",
      { class: "card" },
      el("h3", { text: `Audit trail (${r.audit_trail.length} events)` }),
      el("p", { class: "muted small", text: `Trace ${r.trace_id}. Timestamps come from the fixed clock of deterministic mode.` }),
      el(
        "ol",
        { class: "timeline" },
        r.audit_trail.map((event) =>
          el(
            "li",
            { class: "event" },
            el("span", { class: "event-seq", text: String(event.sequence) }),
            el(
              "div",
              { class: "event-body" },
              el("div", { class: "event-head" }, el("span", { class: "event-stage", text: event.stage }), el("span", { class: "event-name", text: event.event })),
              Object.keys(event.detail).length ? keyValues(Object.entries(event.detail), "compact") : null
            )
          )
        )
      )
    );
  }

  function rawSection(item) {
    return el(
      "section",
      { class: "card raw" },
      el("details", null, el("summary", { text: "Raw result JSON" }), el("pre", { text: JSON.stringify(item.result, null, 2) }))
    );
  }

  // ---- page chrome -------------------------------------------------------

  function renderFooter() {
    const p = DATA.policy;
    document.getElementById("footer").replaceChildren(
      el("p", { text: `Policy ${p.version} (digest ${p.digest.slice(0, 12)}): confidence threshold ${p.min_field_confidence}, submission window ${p.submission_window_days} days, currencies ${p.allowed_currencies.join(", ")}.` }),
      el("p", { text: "All claims, merchants, identifiers and documents are synthetic. Generated by scripts/build_demo_data.py in deterministic mode." })
    );
  }

  function setupTheme() {
    const button = document.getElementById("theme-toggle");
    const order = ["auto", "light", "dark"];
    let theme = "auto";
    try {
      theme = window.localStorage.getItem("adjudication-demo-theme") || "auto";
    } catch (error) {
      theme = "auto";
    }
    const apply = () => {
      if (theme === "auto") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", theme);
      button.textContent = `Theme: ${theme}`;
    };
    button.addEventListener("click", () => {
      theme = order[(order.indexOf(theme) + 1) % order.length];
      try {
        window.localStorage.setItem("adjudication-demo-theme", theme);
      } catch (error) {
        /* storage unavailable: the choice lasts for this page view only */
      }
      apply();
    });
    apply();
  }

  function setupKeyboard() {
    document.getElementById("case-list").addEventListener("keydown", (event) => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const buttons = [...document.querySelectorAll(".case")];
      const index = buttons.indexOf(document.activeElement);
      if (index < 0) return;
      const next = buttons[index + (event.key === "ArrowDown" ? 1 : -1)];
      if (!next) return;
      event.preventDefault();
      next.focus();
      open(next.dataset.key);
    });
  }

  function init() {
    if (!DATA || !Array.isArray(DATA.cases) || !DATA.cases.length) {
      document.getElementById("detail").replaceChildren(
        el("section", { class: "card" }, el("h3", { text: "No demo data found" }), el("p", { text: "Generate it from the repository root with: python scripts/build_demo_data.py" }))
      );
      return;
    }
    for (const rule of DATA.rules) ruleTitles.set(rule.rule_id, rule.title);
    renderFilters();
    renderList();
    renderFooter();
    setupTheme();
    setupKeyboard();
    window.addEventListener("hashchange", () => show(currentHash()));
    show(currentHash() || DATA.cases[0].key);
  }

  init();
})();
