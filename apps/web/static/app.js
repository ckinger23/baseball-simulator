const LINEUP_SIZE = 9;
const BENCH_CANDIDATE_LIMIT = 18;

const state = {
  draft: null,
  draftedLineup: [],
  editedLineup: [],
  draftedBench: [],
  editedBench: [],
  selectedSlot: null,
  dragPayload: null,
  prepared: null,
  recent: [],
  selectedCompareRequestIds: [],
  comparison: null,
};

const els = {
  teamSelect: document.getElementById("team-select"),
  gameDate: document.getElementById("game-date"),
  relieverSelect: document.getElementById("reliever-select"),
  relieverEntryBatter: document.getElementById("reliever-entry-batter"),
  relieverEntryInning: document.getElementById("reliever-entry-inning"),
  mixFf: document.getElementById("mix-ff"),
  mixSl: document.getElementById("mix-sl"),
  mixCh: document.getElementById("mix-ch"),
  prepareForm: document.getElementById("prepare-form"),
  smartDraftBtn: document.getElementById("smart-draft-btn"),
  statusBanner: document.getElementById("status-banner"),
  draftEmpty: document.getElementById("draft-empty"),
  draftContent: document.getElementById("draft-content"),
  draftGame: document.getElementById("draft-game"),
  draftGameMeta: document.getElementById("draft-game-meta"),
  draftPitcher: document.getElementById("draft-pitcher"),
  draftPitcherMeta: document.getElementById("draft-pitcher-meta"),
  draftOpponent: document.getElementById("draft-opponent"),
  draftOpponentMeta: document.getElementById("draft-opponent-meta"),
  draftLineup: document.getElementById("draft-lineup"),
  benchList: document.getElementById("bench-list"),
  benchCount: document.getElementById("bench-count"),
  draftNotes: document.getElementById("draft-notes"),
  resetLineupBtn: document.getElementById("reset-lineup-btn"),
  resultsEmpty: document.getElementById("results-empty"),
  resultsContent: document.getElementById("results-content"),
  metricK: document.getElementById("metric-k"),
  metricBb: document.getElementById("metric-bb"),
  metricBip: document.getElementById("metric-bip"),
  metricHardHit: document.getElementById("metric-hard-hit"),
  metricRunValue: document.getElementById("metric-run-value"),
  matchupSummary: document.getElementById("matchup-summary"),
  simulationGrid: document.getElementById("simulation-grid"),
  projectionList: document.getElementById("projection-list"),
  prepareNotes: document.getElementById("prepare-notes"),
  recentList: document.getElementById("recent-list"),
  heroRecentCount: document.getElementById("hero-recent-count"),
  compareEmpty: document.getElementById("compare-empty"),
  compareContent: document.getElementById("compare-content"),
  compareSummary: document.getElementById("compare-summary"),
  compareNotes: document.getElementById("compare-notes"),
};

function setStatus(message, tone = "info") {
  els.statusBanner.textContent = message;
  els.statusBanner.style.background =
    tone === "error" ? "rgba(126, 31, 24, 0.15)" : "rgba(173, 46, 36, 0.12)";
  els.statusBanner.style.color = tone === "error" ? "#7e1f18" : "#7e1f18";
}

function toPct(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function getPitchMix() {
  return {
    ff: Number(els.mixFf.value || 0),
    sl: Number(els.mixSl.value || 0),
    ch: Number(els.mixCh.value || 0),
  };
}

function normalizeCandidate(player) {
  return {
    hitter_id: player.hitter_id,
    hitter_name: player.hitter_name,
    batting_side: player.batting_side || "R",
    lineup_spot: player.lineup_spot ?? null,
    plate_appearance_count: player.plate_appearance_count ?? null,
  };
}

function clonePlayer(player) {
  return player ? { ...player } : null;
}

function clonePlayerList(players) {
  return players.map((player) => clonePlayer(player));
}

function buildSlotLineup(lineup) {
  const slots = Array.from({ length: LINEUP_SIZE }, () => null);
  lineup.slice(0, LINEUP_SIZE).forEach((player, index) => {
    slots[index] = {
      ...normalizeCandidate(player),
      lineup_spot: index + 1,
    };
  });
  return slots;
}

function reindexLineupSlots(slots) {
  return slots.map((player, index) => (player ? { ...player, lineup_spot: index + 1 } : null));
}

function populatedLineupCount(slots) {
  return slots.filter(Boolean).length;
}

function lineupsMatch(left, right) {
  return left.every((player, index) => {
    const comparison = right[index];
    if (!player && !comparison) {
      return true;
    }
    if (!player || !comparison) {
      return false;
    }
    return player.hitter_id === comparison.hitter_id;
  });
}

function benchesMatch(left, right) {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((player, index) => player.hitter_id === right[index]?.hitter_id);
}

function isWorkbenchEdited() {
  return !lineupsMatch(state.editedLineup, state.draftedLineup) || !benchesMatch(state.editedBench, state.draftedBench);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return response.json();
}

async function loadTeams() {
  const teams = await fetchJson("/teams?season=2025&limit=60");
  els.teamSelect.innerHTML = `<option value="">Choose a team...</option>${teams
    .map((team) => `<option value="${team.team_id}">${team.name} (${team.team_id.toUpperCase()})</option>`)
    .join("")}`;
}

async function loadRecent() {
  try {
    const recent = await fetchJson("/matchups?limit=8");
    state.recent = recent;
    state.selectedCompareRequestIds = state.selectedCompareRequestIds.filter((requestId) =>
      recent.some((item) => item.request_id === requestId)
    );
    els.heroRecentCount.textContent = String(recent.length);
    els.recentList.innerHTML = recent.length
      ? recent
          .map(
            (item) => `
              <article class="recent-item ${
                state.selectedCompareRequestIds.includes(item.request_id) ? "selected-run" : ""
              }">
                <label class="recent-select">
                  <input type="checkbox" data-request-id="${item.request_id}" ${
                    state.selectedCompareRequestIds.includes(item.request_id) ? "checked" : ""
                  } />
                  <strong>${item.pitcher_id} vs ${item.opponent_team_id.toUpperCase()}</strong>
                </label>
                <div class="recent-meta">
                  Saved ${new Date(item.created_at).toLocaleString()} • ${item.status}
                  ${
                    item.simulation
                      ? `• Runs mean ${item.simulation.runs_scored.mean.toFixed(2)}`
                      : ""
                  }
                </div>
              </article>
            `
          )
          .join("")
      : `<div class="empty-state">No saved matchup runs yet. Run one from the panel on the left.</div>`;
    if (state.selectedCompareRequestIds.length === 2) {
      try {
        await loadComparison();
      } catch (error) {
        clearComparison();
        setStatus(`Compare error: ${error.message}`, "error");
      }
    } else {
      clearComparison();
    }
  } catch (_error) {
    els.recentList.innerHTML = `<div class="empty-state">Could not load recent runs.</div>`;
  }
}

function clearComparison() {
  state.comparison = null;
  els.compareEmpty.classList.remove("hidden");
  els.compareContent.classList.add("hidden");
  els.compareSummary.innerHTML = "";
  els.compareNotes.textContent = "";
}

async function loadComparison() {
  if (state.selectedCompareRequestIds.length !== 2) {
    clearComparison();
    return;
  }

  const comparison = await fetchJson("/matchups/compare", {
    method: "POST",
    body: JSON.stringify({ request_ids: state.selectedCompareRequestIds }),
  });
  state.comparison = comparison;
  const delta = comparison.deltas[0];
  const cards = [
    ["Runs Delta", delta.runs_scored_mean_delta, "mean runs"],
    ["Home Run Delta", delta.home_runs_mean_delta, "mean HR"],
    ["K Rate Delta", delta.expected_k_rate_delta, "rate change"],
    ["BB Rate Delta", delta.expected_bb_rate_delta, "rate change"],
    ["Run Value Delta", delta.run_value_mean_delta, "mean value"],
  ];
  els.compareEmpty.classList.add("hidden");
  els.compareContent.classList.remove("hidden");
  els.compareSummary.innerHTML = cards
    .map(
      ([label, value, suffix]) => `
        <article class="compare-card">
          <strong>${label}</strong>
          <span>${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(3)} ${suffix}</span>
        </article>
      `
    )
    .join("");

  const runsDelta = Number(delta.runs_scored_mean_delta);
  const homeRunDelta = Number(delta.home_runs_mean_delta);
  const read =
    runsDelta > 0
      ? `The comparison scenario projects ${runsDelta.toFixed(2)} more runs on average than the baseline, with a ${
          homeRunDelta >= 0 ? "higher" : "lower"
        } home run expectation.`
      : `The comparison scenario projects ${Math.abs(runsDelta).toFixed(2)} fewer runs on average than the baseline, which suggests the alternate pitching plan is suppressing damage better.`;
  els.compareNotes.textContent = read;
}

async function loadBenchCandidates(teamId, draftedLineup) {
  const candidates = await fetchJson(`/teams/${teamId}/lineup-candidates?limit=${BENCH_CANDIDATE_LIMIT}`);
  const draftedIds = new Set(draftedLineup.filter(Boolean).map((player) => player.hitter_id));
  return candidates.map(normalizeCandidate).filter((player) => !draftedIds.has(player.hitter_id));
}

async function loadBullpenCandidates(teamId) {
  try {
    return await fetchJson(`/teams/${teamId}/bullpen-candidates?limit=12`);
  } catch (_error) {
    return [];
  }
}

function renderRelieverOptions(candidates, starterPitcherId = null) {
  const filtered = candidates.filter((candidate) => candidate.pitcher_id !== starterPitcherId);
  els.relieverSelect.innerHTML =
    `<option value="">Starter Only</option>` +
    filtered
      .map(
        (candidate) =>
          `<option value="${candidate.pitcher_id}" data-name="${candidate.pitcher_name}">${candidate.pitcher_name} (${candidate.throws || "?"})</option>`
      )
      .join("");
}

function setDraftWorkbench(draft, benchPlayers) {
  state.draft = draft;
  state.draftedLineup = buildSlotLineup(draft.lineup);
  state.editedLineup = clonePlayerList(state.draftedLineup);
  state.draftedBench = clonePlayerList(benchPlayers);
  state.editedBench = clonePlayerList(benchPlayers);
  state.selectedSlot = null;
  state.dragPayload = null;
}

function renderLineupBoard() {
  els.draftLineup.innerHTML = state.editedLineup
    .map((player, index) => {
      const isSelected = state.selectedSlot === index;
      const hasPlayer = Boolean(player);
      return `
        <article
          class="slot-card ${hasPlayer ? "slot-filled" : "slot-empty"} ${isSelected ? "slot-selected" : ""}"
          data-drop-target="lineup-slot"
          data-slot-index="${index}"
        >
          <div class="slot-badge">Slot ${index + 1}</div>
          ${
            hasPlayer
              ? `
                <div
                  class="slot-player"
                  draggable="true"
                  data-drag-source="lineup"
                  data-slot-index="${index}"
                >
                  <strong>${player.hitter_name}</strong>
                  <div class="lineup-meta">${player.hitter_id} • ${player.batting_side || "?"}-side</div>
                  <div class="lineup-meta">${
                    player.plate_appearance_count == null ? "Manual slot" : `${player.plate_appearance_count} PA`
                  }</div>
                </div>
              `
              : `<div class="slot-placeholder">Drop a bench hitter here</div>`
          }
        </article>
      `;
    })
    .join("");
}

function renderBenchBoard() {
  const benchCount = state.editedBench.length;
  els.benchCount.textContent = `${benchCount} available`;
  els.benchCount.classList.toggle("hidden", benchCount === 0);
  els.benchList.innerHTML = benchCount
    ? state.editedBench
        .map(
          (player, index) => `
            <article
              class="bench-card"
              draggable="true"
              data-drag-source="bench"
              data-bench-index="${index}"
              data-drop-target="bench-card"
              data-bench-target-index="${index}"
            >
              <strong>${player.hitter_name}</strong>
              <div class="lineup-meta">${player.hitter_id} • ${player.batting_side || "?"}-side</div>
              <div class="lineup-meta">${
                player.plate_appearance_count == null ? "Candidate" : `${player.plate_appearance_count} PA`
              }</div>
            </article>
          `
        )
        .join("")
    : `<div class="empty-state compact-empty">No extra hitters are available in the current local candidate pool.</div>`;
}

function renderDraftWorkbench() {
  els.resetLineupBtn.classList.toggle("hidden", !isWorkbenchEdited());
  renderLineupBoard();
  renderBenchBoard();
}

function renderDraft(draft) {
  els.draftEmpty.classList.add("hidden");
  els.draftContent.classList.remove("hidden");
  els.draftGame.textContent = `${draft.selected_game.away_team_name} at ${draft.selected_game.home_team_name}`;
  els.draftGameMeta.textContent = `${draft.selected_game.game_date} • ${draft.selected_game.status}`;
  els.draftPitcher.textContent = draft.pitcher.pitcher_name;
  els.draftPitcherMeta.textContent = `${draft.pitcher.throws || "?"}-handed • ${draft.pitcher.pitcher_id}`;
  els.draftOpponent.textContent = `${draft.opponent_team.name} (${draft.opponent_team.team_id.toUpperCase()})`;
  els.draftOpponentMeta.textContent = `${draft.opponent_team.league} • ${draft.opponent_team.season}`;
  renderDraftWorkbench();
  els.draftNotes.innerHTML = draft.notes.map((note) => `<li>${note}</li>`).join("");
}

function renderPrepared(prepared) {
  state.prepared = prepared;
  const matchup = prepared.matchup;
  els.resultsEmpty.classList.add("hidden");
  els.resultsContent.classList.remove("hidden");
  els.metricK.textContent = toPct(matchup.overview.expected_k_rate);
  els.metricBb.textContent = toPct(matchup.overview.expected_bb_rate);
  els.metricBip.textContent = toPct(matchup.overview.expected_bip_rate);
  els.metricHardHit.textContent = toPct(matchup.overview.expected_hard_hit_rate);
  els.metricRunValue.textContent = matchup.overview.estimated_run_value.toFixed(3);
  els.matchupSummary.textContent = matchup.overview.summary;

  const simulationEntries = [
    ["Runs Scored", matchup.simulation.runs_scored],
    ["Hits", matchup.simulation.hits],
    ["Home Runs", matchup.simulation.home_runs],
    ["Plate Appearances", matchup.simulation.plate_appearances],
    ["Strikeouts", matchup.simulation.strikeouts],
    ["Walks", matchup.simulation.walks],
    ["Inherited Runners", matchup.simulation.reliever_inherited_runners],
    ["Inherited Runners Scored", matchup.simulation.reliever_inherited_runners_scored],
  ];
  els.simulationGrid.innerHTML = simulationEntries
    .map(
      ([label, dist]) => `
        <article class="sim-card">
          <strong>${label}</strong>
          <span>Mean ${dist.mean.toFixed(2)}<br />P10 ${dist.p10.toFixed(2)} • P50 ${dist.p50.toFixed(
            2
          )} • P90 ${dist.p90.toFixed(2)}</span>
        </article>
      `
    )
    .join("");

  els.projectionList.innerHTML = matchup.hitter_projections
    .slice(0, 5)
    .map(
      (projection) => `
        <article class="projection-item">
          <div>
            <strong>${projection.hitter_name}</strong>
            <div class="projection-meta">
              K ${toPct(projection.estimated_k_rate)} • BB ${toPct(projection.estimated_bb_rate)} • Focus ${
                projection.pitch_type_focus
              }
            </div>
          </div>
          <div class="projection-meta">Run value ${projection.estimated_run_value.toFixed(3)}</div>
        </article>
      `
    )
    .join("");

  els.prepareNotes.innerHTML = prepared.notes.map((note) => `<li>${note}</li>`).join("");
}

function clearDragState() {
  state.dragPayload = null;
  document.querySelectorAll(".drag-over").forEach((node) => node.classList.remove("drag-over"));
}

function selectSlot(index) {
  state.selectedSlot = state.selectedSlot === index ? null : index;
  renderDraftWorkbench();
}

function swapLineupSlots(sourceIndex, targetIndex) {
  const nextLineup = clonePlayerList(state.editedLineup);
  [nextLineup[sourceIndex], nextLineup[targetIndex]] = [nextLineup[targetIndex], nextLineup[sourceIndex]];
  state.editedLineup = reindexLineupSlots(nextLineup);
  state.selectedSlot = targetIndex;
  renderDraftWorkbench();
}

function moveBenchPlayerToSlot(benchIndex, slotIndex) {
  const benchPlayer = state.editedBench[benchIndex];
  if (!benchPlayer) {
    return;
  }
  const nextLineup = clonePlayerList(state.editedLineup);
  const nextBench = clonePlayerList(state.editedBench);
  const outgoingPlayer = nextLineup[slotIndex];
  nextLineup[slotIndex] = clonePlayer(benchPlayer);
  if (outgoingPlayer) {
    nextBench[benchIndex] = clonePlayer(outgoingPlayer);
  } else {
    nextBench.splice(benchIndex, 1);
  }
  state.editedLineup = reindexLineupSlots(nextLineup);
  state.editedBench = nextBench;
  state.selectedSlot = slotIndex;
  renderDraftWorkbench();
}

function handleDropToLineupSlot(slotIndex) {
  if (!state.dragPayload) {
    return;
  }
  if (state.dragPayload.sourceType === "lineup") {
    swapLineupSlots(state.dragPayload.slotIndex, slotIndex);
    setStatus("Reordered the lineup card.");
    return;
  }
  if (state.dragPayload.sourceType === "bench") {
    moveBenchPlayerToSlot(state.dragPayload.benchIndex, slotIndex);
    setStatus("Swapped a bench hitter into the lineup.");
  }
}

function handleDropToBenchCard(benchIndex) {
  if (!state.dragPayload || state.dragPayload.sourceType !== "lineup") {
    return;
  }
  moveBenchPlayerToSlot(benchIndex, state.dragPayload.slotIndex);
}

function attachBenchPlayerToSelectedSlot(benchIndex) {
  if (state.selectedSlot == null) {
    return;
  }
  moveBenchPlayerToSlot(benchIndex, state.selectedSlot);
  setStatus(`Updated slot ${state.selectedSlot + 1} from the bench pool.`);
}

async function previewDraft() {
  const teamId = els.teamSelect.value;
  const gameDate = els.gameDate.value;

  if (!teamId || !gameDate) {
    setStatus("Choose both a team and a game date before previewing the draft.", "error");
    return;
  }

  setStatus("Pulling the live scheduled game, probable pitcher, and local 9-man lineup candidates...");
  const draft = await fetchJson("/matchups/smart-draft", {
    method: "POST",
    body: JSON.stringify({ team_id: teamId, game_date: gameDate, lineup_size: LINEUP_SIZE }),
  });
  const draftedSlots = buildSlotLineup(draft.lineup);
  const [benchPlayers, bullpenCandidates] = await Promise.all([
    loadBenchCandidates(teamId, draftedSlots),
    loadBullpenCandidates(draft.opponent_team.team_id),
  ]);
  setDraftWorkbench(draft, benchPlayers);
  renderRelieverOptions(bullpenCandidates, draft.pitcher.pitcher_id);
  renderDraft(draft);
  setStatus("Draft ready. Drag hitters across slots or swap in someone from the bench before you run the matchup.");
}

function lineupOverridePayload() {
  return state.editedLineup
    .filter(Boolean)
    .map((player, index) => ({
      hitter_id: player.hitter_id,
      hitter_name: player.hitter_name,
      batting_side: player.batting_side || "R",
      lineup_spot: index + 1,
    }));
}

async function prepareAndRun(event) {
  event.preventDefault();
  const teamId = els.teamSelect.value;
  const gameDate = els.gameDate.value;

  if (!teamId || !gameDate) {
    setStatus("Choose both a team and a game date before running the matchup.", "error");
    return;
  }

  if (populatedLineupCount(state.editedLineup) < LINEUP_SIZE) {
    setStatus("Fill all 9 lineup slots before running the matchup.", "error");
    return;
  }

  const relieverId = els.relieverSelect.value || null;
  const relieverName = relieverId
    ? els.relieverSelect.options[els.relieverSelect.selectedIndex]?.dataset?.name || null
    : null;
  const relieverEntryBatter = relieverId ? Number(els.relieverEntryBatter.value || 19) : null;
  const relieverEntryInning = relieverId ? Number(els.relieverEntryInning.value || 7) : null;

  setStatus("Preparing the matchup, applying pitch mix, running the simulation, and saving the result...");
  const prepared = await fetchJson("/matchups/prepare", {
    method: "POST",
    body: JSON.stringify({
      team_id: teamId,
      game_date: gameDate,
      lineup_size: LINEUP_SIZE,
      lineup_override: lineupOverridePayload(),
      reliever_id: relieverId,
      reliever_name: relieverName,
      reliever_entry_batter_number: relieverEntryBatter,
      reliever_entry_inning: relieverEntryInning,
      manual_pitch_mix_adjustments: getPitchMix(),
    }),
  });
  const [benchPlayers, bullpenCandidates] = await Promise.all([
    loadBenchCandidates(teamId, buildSlotLineup(prepared.draft.lineup)),
    loadBullpenCandidates(prepared.draft.opponent_team.team_id),
  ]);
  setDraftWorkbench(prepared.draft, benchPlayers);
  renderRelieverOptions(bullpenCandidates, prepared.draft.pitcher.pitcher_id);
  if (relieverId) {
    els.relieverSelect.value = relieverId;
    els.relieverEntryBatter.value = String(relieverEntryBatter || 19);
    els.relieverEntryInning.value = String(relieverEntryInning || 7);
  }
  renderDraft(prepared.draft);
  renderPrepared(prepared);
  await loadRecent();
  setStatus("Prepared matchup complete and saved. Drag the order around, tune the pitch mix, or add a reliever scenario and run another version.");
}

function toggleCompareSelection(requestId, checked) {
  if (checked) {
    if (state.selectedCompareRequestIds.includes(requestId)) {
      return;
    }
    if (state.selectedCompareRequestIds.length >= 2) {
      state.selectedCompareRequestIds = [state.selectedCompareRequestIds[1], requestId];
    } else {
      state.selectedCompareRequestIds = [...state.selectedCompareRequestIds, requestId];
    }
  } else {
    state.selectedCompareRequestIds = state.selectedCompareRequestIds.filter((item) => item !== requestId);
  }
}

function handleDraftWorkbenchClick(event) {
  const slot = event.target.closest("[data-slot-index]");
  if (slot) {
    selectSlot(Number(slot.dataset.slotIndex));
    return;
  }

  const benchCard = event.target.closest("[data-bench-index]");
  if (benchCard) {
    attachBenchPlayerToSelectedSlot(Number(benchCard.dataset.benchIndex));
  }
}

function handleRecentListChange(event) {
  const checkbox = event.target.closest("[data-request-id]");
  if (!checkbox) {
    return;
  }
  toggleCompareSelection(checkbox.dataset.requestId, checkbox.checked);
  loadRecent().catch((error) => setStatus(`Compare error: ${error.message}`, "error"));
}

function handleDragStart(event) {
  const source = event.target.closest("[data-drag-source]");
  if (!source) {
    return;
  }

  if (source.dataset.dragSource === "lineup") {
    state.dragPayload = { sourceType: "lineup", slotIndex: Number(source.dataset.slotIndex) };
  } else if (source.dataset.dragSource === "bench") {
    state.dragPayload = { sourceType: "bench", benchIndex: Number(source.dataset.benchIndex) };
  }

  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", JSON.stringify(state.dragPayload));
  }
}

function handleDragOver(event) {
  const target = event.target.closest("[data-drop-target]");
  if (!target || !state.dragPayload) {
    return;
  }
  event.preventDefault();
  target.classList.add("drag-over");
}

function handleDragLeave(event) {
  const target = event.target.closest("[data-drop-target]");
  if (!target) {
    return;
  }
  target.classList.remove("drag-over");
}

function handleDrop(event) {
  const target = event.target.closest("[data-drop-target]");
  if (!target) {
    return;
  }
  event.preventDefault();
  target.classList.remove("drag-over");

  if (target.dataset.dropTarget === "lineup-slot") {
    handleDropToLineupSlot(Number(target.dataset.slotIndex));
  }

  if (target.dataset.dropTarget === "bench-card") {
    handleDropToBenchCard(Number(target.dataset.benchTargetIndex));
    if (state.dragPayload?.sourceType === "lineup") {
      setStatus("Swapped a lineup hitter with someone from the bench.");
    }
  }

  clearDragState();
}

async function init() {
  const today = new Date("2025-06-03T12:00:00");
  els.gameDate.value = today.toISOString().slice(0, 10);
  try {
    await loadTeams();
    await loadRecent();
    setStatus("Ready. Start by choosing a team and date.");
  } catch (error) {
    setStatus(`Startup error: ${error.message}`, "error");
  }
}

els.smartDraftBtn.addEventListener("click", () => {
  previewDraft().catch((error) => setStatus(`Draft error: ${error.message}`, "error"));
});

els.draftLineup.addEventListener("click", handleDraftWorkbenchClick);
els.benchList.addEventListener("click", handleDraftWorkbenchClick);
els.recentList.addEventListener("change", handleRecentListChange);
els.draftLineup.addEventListener("dragstart", handleDragStart);
els.benchList.addEventListener("dragstart", handleDragStart);
els.draftLineup.addEventListener("dragover", handleDragOver);
els.benchList.addEventListener("dragover", handleDragOver);
els.draftLineup.addEventListener("dragleave", handleDragLeave);
els.benchList.addEventListener("dragleave", handleDragLeave);
els.draftLineup.addEventListener("drop", handleDrop);
els.benchList.addEventListener("drop", handleDrop);
els.draftLineup.addEventListener("dragend", clearDragState);
els.benchList.addEventListener("dragend", clearDragState);

els.resetLineupBtn.addEventListener("click", () => {
  state.editedLineup = clonePlayerList(state.draftedLineup);
  state.editedBench = clonePlayerList(state.draftedBench);
  state.selectedSlot = null;
  renderDraftWorkbench();
  setStatus("Restored the original smart draft lineup and bench pool.");
});

els.relieverSelect.addEventListener("change", () => {
  if (!els.relieverSelect.value) {
    setStatus("Starter-only scenario selected.");
    return;
  }
  const relieverName = els.relieverSelect.options[els.relieverSelect.selectedIndex]?.dataset?.name || "Selected reliever";
  setStatus(`${relieverName} is set as the late-game handoff option.`);
});

els.prepareForm.addEventListener("submit", (event) => {
  prepareAndRun(event).catch((error) => setStatus(`Prepare error: ${error.message}`, "error"));
});

init();
