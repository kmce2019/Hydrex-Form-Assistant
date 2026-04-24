let currentProjectId = null;
let currentTceqCsv = '';
let latestResults = {};

const formContainer = document.getElementById('intakeForm');
const savedProjects = document.getElementById('savedProjects');
const loadBtn = document.getElementById('loadBtn');
const newBtn = document.getElementById('newBtn');
const saveBtn = document.getElementById('saveBtn');
const exportBtn = document.getElementById('exportBtn');
const runSearchBtn = document.getElementById('runSearchBtn');
const generateBtn = document.getElementById('generateBtn');
const explosiveOutput = document.getElementById('explosiveOutput');
const contaminationOutput = document.getElementById('contaminationOutput');
const checklistOutput = document.getElementById('checklistOutput');
const evidenceChecklist = document.getElementById('evidenceChecklist');
const searchStatus = document.getElementById('searchStatus');
const tceqFile = document.getElementById('tceqFile');

const rcraCard = document.getElementById('rcraCard');
const lpstCard = document.getElementById('lpstCard');
const pstCard = document.getElementById('pstCard');
const nearestCard = document.getElementById('nearestCard');

const map = L.map('map').setView([31.0, -99.0], 5);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

const layerGroup = L.layerGroup().addTo(map);

function allFields() {
  return Array.from(formContainer.querySelectorAll('input[name]:not([type="checkbox"]), select[name], textarea[name]'));
}

function selectedSources() {
  return Array.from(document.querySelectorAll('input[name="source_check"]:checked')).map((el) => el.value);
}

function setSelectedSources(values = []) {
  document.querySelectorAll('input[name="source_check"]').forEach((el) => {
    el.checked = values.includes(el.value);
  });

function allFields() {
  return Array.from(formContainer.querySelectorAll('input[name], select[name], textarea[name]'));
}

function collectPayload() {
  const payload = {};
  allFields().forEach((field) => {
    payload[field.name] = field.value;
  });

  if (latestResults && Object.keys(latestResults).length > 0) {
    payload.environmental_results_json = JSON.stringify(latestResults);
    payload.source_tracking_json = JSON.stringify(latestResults.source_tracking || {});
    payload.buffer_half_mile_json = JSON.stringify(latestResults.buffers?.half_mile || {});
    payload.buffer_one_mile_json = JSON.stringify(latestResults.buffers?.one_mile || {});

    payload.rcra_count = latestResults.rcra_count_half_mile ?? payload.rcra_count;
    payload.lpst_count = latestResults.lpst_count_half_mile ?? payload.lpst_count;
    payload.pst_count = latestResults.pst_count_one_mile ?? payload.pst_count;
  }

  if (currentProjectId) payload.id = currentProjectId;
  if (currentProjectId) {
    payload.id = currentProjectId;
  }
  return payload;
}

function fillForm(data) {
  allFields().forEach((field) => {
    field.value = data[field.name] ?? '';
  });
  const results = data.environmental_results_json ? JSON.parse(data.environmental_results_json) : {};
  latestResults = results;
  setSelectedSources(results.sources_used || []);
  renderResults(results);
}

function resetForm() {
  currentProjectId = null;
  latestResults = {};
  currentTceqCsv = '';
  allFields().forEach((field) => {
    if (field.type === 'number') field.value = '0';
    else field.value = '';
  });
  setSelectedSources([]);
  checklistOutput.innerHTML = '';
  evidenceChecklist.innerHTML = '';
  explosiveOutput.value = '';
  contaminationOutput.value = '';
  searchStatus.textContent = '';
  rcraCard.textContent = lpstCard.textContent = pstCard.textContent = nearestCard.textContent = '-';
  layerGroup.clearLayers();
}

function renderResults(results = {}) {
  rcraCard.textContent = results.rcra_count_half_mile ?? '-';
  lpstCard.textContent = results.lpst_count_half_mile ?? '-';
  pstCard.textContent = results.pst_count_one_mile ?? '-';
  nearestCard.textContent = results.nearest_facility_miles !== undefined && results.nearest_facility_miles !== null
    ? `${results.nearest_facility_miles} miles`
    : '-';

  evidenceChecklist.innerHTML = '';
  (results.evidence_checklist || []).forEach((item) => {
    const li = document.createElement('li');
    li.textContent = `${item.present ? '☑' : '☐'} ${item.item}`;
    if (!item.present) li.classList.add('missing');
    evidenceChecklist.appendChild(li);
  });

  if ((results.rcra_count_half_mile || 0) === 0 && (results.lpst_count_half_mile || 0) === 0) {
    const contaminationNotes = document.querySelector('[name="contamination_sources_notes"]');
    if (contaminationNotes && !contaminationNotes.value.trim()) {
      contaminationNotes.value = 'No hazardous or toxic substances were identified within the search radius based on database review.';
    }
  }

  renderMap(results);
}

function renderMap(results = {}) {
  layerGroup.clearLayers();
  if (!results.latitude || !results.longitude) return;

  const center = [results.latitude, results.longitude];
  L.marker(center).addTo(layerGroup).bindPopup('Project Location');
  L.circle(center, { radius: 804.67, color: '#9333ea', fillOpacity: 0.08 }).addTo(layerGroup).bindPopup('0.5 mile buffer');
  L.circle(center, { radius: 1609.34, color: '#2563eb', fillOpacity: 0.08 }).addTo(layerGroup).bindPopup('1 mile buffer');

  (results.epa_facilities || []).slice(0, 40).forEach((site) => {
    if (site.latitude == null || site.longitude == null) return;
    L.circleMarker([site.latitude, site.longitude], { radius: 5, color: '#ef4444' })
      .addTo(layerGroup)
      .bindPopup(`EPA Facility: ${site.name}`);
  });

  (results.tceq_sites || []).slice(0, 50).forEach((site) => {
    if (site.latitude == null || site.longitude == null) return;
    L.circleMarker([site.latitude, site.longitude], { radius: 5, color: '#16a34a' })
      .addTo(layerGroup)
      .bindPopup(`TCEQ ${site.type}: ${site.name}`);
  });

  map.setView(center, 13);
  checklistOutput.innerHTML = '';
  explosiveOutput.value = '';
  contaminationOutput.value = '';
}

async function refreshProjects() {
  const res = await fetch('/api/projects');
  const projects = await res.json();

  savedProjects.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.textContent = '-- Select a project --';
  placeholder.value = '';
  savedProjects.appendChild(placeholder);

  projects.forEach((project) => {
    const option = document.createElement('option');
    option.value = project.id;
    option.textContent = `${project.project_name} (${project.client || 'No client'})`;
    savedProjects.appendChild(option);
  });
}

async function saveProject() {
  const payload = collectPayload();
  if (!payload.project_name?.trim()) {
  if (!payload.project_name.trim()) {
    alert('Project name is required.');
    return;
  }

  const res = await fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const project = await res.json();
  currentProjectId = project.id;
  await refreshProjects();
  savedProjects.value = String(project.id);
  alert('Project saved.');
}

async function loadProject() {
  const id = savedProjects.value;
  if (!id) return;

  const res = await fetch(`/api/projects/${id}`);
  if (!res.ok) {
    alert('Could not load project.');
    return;
  }
  const project = await res.json();
  currentProjectId = project.id;
  fillForm(project);
}

async function runEnvironmentalSearch() {
  const project = collectPayload();
  searchStatus.textContent = 'Running geocode + EPA/TCEQ search...';
  runSearchBtn.disabled = true;

  try {
    const res = await fetch('/api/environmental-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project,
        tceq_csv: currentTceqCsv,
        selected_sources: selectedSources()
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Search failed');
    }

    latestResults = data;
    const latField = document.querySelector('[name="latitude"]');
    const lonField = document.querySelector('[name="longitude"]');
    latField.value = data.latitude;
    lonField.value = data.longitude;

    document.querySelector('[name="rcra_count"]').value = data.rcra_count_half_mile ?? 0;
    document.querySelector('[name="lpst_count"]').value = data.lpst_count_half_mile ?? 0;
    document.querySelector('[name="pst_count"]').value = data.pst_count_one_mile ?? 0;

    renderResults(data);
    searchStatus.textContent = 'Environmental search complete. Review results and save.';
  } catch (error) {
    searchStatus.textContent = `Search failed: ${error.message}`;
  } finally {
    runSearchBtn.disabled = false;
  }
}

async function generateSummaries() {
  const payload = collectPayload();
  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();

  explosiveOutput.value = data.explosive_summary;
  contaminationOutput.value = data.contamination_summary;

  checklistOutput.innerHTML = '';
  (data.missing_evidence || []).forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    checklistOutput.appendChild(li);
  });
}

function exportMarkdown() {
  if (data.missing_evidence.length === 0) {
    const li = document.createElement('li');
    li.textContent = 'No obvious gaps detected from provided fields; complete final staff review.';
    checklistOutput.appendChild(li);
  } else {
    data.missing_evidence.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
      checklistOutput.appendChild(li);
    });
  }
}

async function exportMarkdown() {
  if (!currentProjectId) {
    alert('Save the project before export.');
    return;
  }
  window.location.href = `/api/projects/${currentProjectId}/export`;
}

async function copyFromTarget(event) {
  const targetId = event.target.dataset.target;
  const text = document.getElementById(targetId)?.value || '';
  if (!text) return;
  await navigator.clipboard.writeText(text);
  event.target.textContent = 'Copied!';
  setTimeout(() => {
    event.target.textContent = 'Copy';
  }, 1000);
}

tceqFile.addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) {
    currentTceqCsv = '';
    return;
  }
  currentTceqCsv = await file.text();
});

document.querySelectorAll('.copy-btn').forEach((btn) => btn.addEventListener('click', copyFromTarget));
loadBtn.addEventListener('click', loadProject);
newBtn.addEventListener('click', resetForm);
saveBtn.addEventListener('click', saveProject);
exportBtn.addEventListener('click', exportMarkdown);
generateBtn.addEventListener('click', generateSummaries);
runSearchBtn.addEventListener('click', runEnvironmentalSearch);

refreshProjects();
