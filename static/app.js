let currentProjectId = null;
let currentTceqCsv = '';
let latestResults = {};
let selectedTank = null;

const formContainer = document.getElementById('intakeForm');
const savedProjects = document.getElementById('savedProjects');
const loadBtn = document.getElementById('loadBtn');
const newBtn = document.getElementById('newBtn');
const saveBtn = document.getElementById('saveBtn');
const exportBtn = document.getElementById('exportBtn');
const exportPdfBtn = document.getElementById('exportPdfBtn');
const runSearchBtn = document.getElementById('runSearchBtn');
const generateBtn = document.getElementById('generateBtn');
const clearTankBtn = document.getElementById('clearTankBtn');

const explosiveOutput = document.getElementById('explosiveOutput');
const contaminationOutput = document.getElementById('contaminationOutput');
const checklistOutput = document.getElementById('checklistOutput');
const evidenceChecklist = document.getElementById('evidenceChecklist');
const searchStatus = document.getElementById('searchStatus');
const tceqFile = document.getElementById('tceqFile');
const hudAnswersPre = document.getElementById('hudAnswers');
const selectedTankDetails = document.getElementById('selectedTankDetails');

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
}

function setStatus(text, kind = 'info') {
  searchStatus.textContent = text;
  searchStatus.className = `status ${kind}`;
}

function updateSelectedTankPanel() {
  if (!selectedTank) {
    selectedTankDetails.textContent = 'No tank selected.';
    return;
  }
  selectedTankDetails.innerHTML = `
    <strong>${selectedTank.name || 'Unnamed'}</strong><br>
    Type: ${selectedTank.type || 'Unknown'}<br>
    Status: ${selectedTank.status || 'Unknown'}<br>
    Distance: ${selectedTank.distance_miles ?? 'unknown'} miles<br>
    Lat/Lon: ${selectedTank.latitude ?? 'n/a'}, ${selectedTank.longitude ?? 'n/a'}<br>
    Capacity: ${selectedTank.capacity || 'not documented'}<br>
    Contents: ${selectedTank.contents || 'not documented'}
  `;
}

window.selectAssessedTankByIndex = function selectAssessedTankByIndex(index) {
  const sites = latestResults.tceq_sites || [];
  selectedTank = sites[index] || null;
  if (selectedTank) selectedTank.asd_status = selectedTank.distance_miles > 0.75 ? 'preliminarily acceptable' : 'review required';
  updateSelectedTankPanel();
  renderMap(latestResults);
  setStatus('Selected assessed tank updated. Save project to persist selection.');
};

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
    payload.selected_tank_json = JSON.stringify(selectedTank || {});

    payload.rcra_count = latestResults.rcra_count_half_mile ?? payload.rcra_count;
    payload.lpst_count = latestResults.lpst_count_half_mile ?? payload.lpst_count;
    payload.pst_count = latestResults.pst_count_one_mile ?? payload.pst_count;
  }

  if (currentProjectId) payload.id = currentProjectId;
  return payload;
}

function fillForm(data) {
  allFields().forEach((field) => {
    field.value = data[field.name] ?? '';
  });
  const results = data.environmental_results_json ? JSON.parse(data.environmental_results_json) : {};
  latestResults = results;
  selectedTank = data.selected_tank_json ? JSON.parse(data.selected_tank_json) : null;
  setSelectedSources(results.sources_used || []);
  updateSelectedTankPanel();
  renderResults(results);
}

function resetForm() {
  currentProjectId = null;
  latestResults = {};
  selectedTank = null;
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
  hudAnswersPre.textContent = 'Run Generate Summaries to populate HUD answers.';
  setStatus('');
  rcraCard.textContent = lpstCard.textContent = pstCard.textContent = nearestCard.textContent = '-';
  layerGroup.clearLayers();
  updateSelectedTankPanel();
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
    li.classList.add(item.present ? 'present' : 'missing');
    evidenceChecklist.appendChild(li);
  });

  renderMap(results);
}

function renderMap(results = {}) {
  layerGroup.clearLayers();
  if (!results.latitude || !results.longitude) return;

  const center = [results.latitude, results.longitude];
  L.marker(center, { title: 'Project' }).addTo(layerGroup).bindPopup('Project Location');
  L.circle(center, { radius: 804.67, color: '#9333ea', fillOpacity: 0.08 }).addTo(layerGroup).bindPopup('0.5 mile buffer');
  L.circle(center, { radius: 1609.34, color: '#2563eb', fillOpacity: 0.08 }).addTo(layerGroup).bindPopup('1 mile buffer');

  (results.epa_facilities || []).slice(0, 50).forEach((site) => {
    if (site.latitude == null || site.longitude == null) return;
    L.circleMarker([site.latitude, site.longitude], { radius: 5, color: '#ef4444' })
      .addTo(layerGroup)
      .bindPopup(`<strong>RCRA/EPA</strong><br>${site.name}<br>Type: ${site.type}<br>Status: ${site.status}<br>Distance: ${site.distance_miles ?? 'n/a'} mi`);
  });

  (results.tceq_sites || []).slice(0, 100).forEach((site, index) => {
    if (site.latitude == null || site.longitude == null) return;
    let color = '#16a34a';
    if ((site.type || '').includes('LPST')) color = '#f59e0b';
    if ((site.type || '').includes('PST') || (site.type || '').includes('TANK')) color = '#0ea5e9';
    if (selectedTank && selectedTank.name === site.name && selectedTank.distance_miles === site.distance_miles) color = '#7c3aed';

    L.circleMarker([site.latitude, site.longitude], { radius: selectedTank && selectedTank.name === site.name ? 8 : 6, color })
      .addTo(layerGroup)
      .bindPopup(`
        <strong>${site.type}</strong><br>
        ${site.name}<br>
        Status: ${site.status}<br>
        Distance: ${site.distance_miles} mi<br>
        Capacity: ${site.capacity || 'n/a'}<br>
        Contents: ${site.contents || 'n/a'}<br>
        <button type="button" onclick="window.selectAssessedTankByIndex(${index})">Select as assessed tank</button>
      `);
  });

  map.setView(center, 13);
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
  setStatus('Project saved.', 'success');
}

async function loadProject() {
  const id = savedProjects.value;
  if (!id) return;

  const res = await fetch(`/api/projects/${id}`);
  if (!res.ok) {
    setStatus('Could not load project.', 'error');
    return;
  }
  const project = await res.json();
  currentProjectId = project.id;
  fillForm(project);
  setStatus('Project loaded.', 'success');
}

async function runEnvironmentalSearch() {
  const project = collectPayload();
  setStatus('Running geocode + EPA/TCEQ search...', 'info');
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
    document.querySelector('[name="latitude"]').value = data.latitude;
    document.querySelector('[name="longitude"]').value = data.longitude;

    document.querySelector('[name="rcra_count"]').value = data.rcra_count_half_mile ?? 0;
    document.querySelector('[name="lpst_count"]').value = data.lpst_count_half_mile ?? 0;
    document.querySelector('[name="pst_count"]').value = data.pst_count_one_mile ?? 0;

    renderResults(data);
    setStatus('Environmental search complete. Review results and save.', 'success');
  } catch (error) {
    setStatus(`Search failed: ${error.message}. You can still enter data manually.`, 'error');
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
  hudAnswersPre.textContent = JSON.stringify(data.hud_answers, null, 2);

  checklistOutput.innerHTML = '';
  (data.missing_evidence || []).forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    li.classList.add('missing');
    checklistOutput.appendChild(li);
  });

}

function exportMarkdown() {
  if (!currentProjectId) {
    alert('Save the project before export.');
    return;
  }
  window.location.href = `/api/projects/${currentProjectId}/export`;
}

function exportPdf() {
  if (!currentProjectId) {
    alert('Save the project before export.');
    return;
  }
  window.location.href = `/api/projects/${currentProjectId}/export/pdf`;
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
  setStatus('Loaded TCEQ CSV file.', 'success');
});

document.querySelectorAll('.copy-btn').forEach((btn) => btn.addEventListener('click', copyFromTarget));
loadBtn.addEventListener('click', loadProject);
newBtn.addEventListener('click', resetForm);
saveBtn.addEventListener('click', saveProject);
exportBtn.addEventListener('click', exportMarkdown);
exportPdfBtn.addEventListener('click', exportPdf);
generateBtn.addEventListener('click', generateSummaries);
runSearchBtn.addEventListener('click', runEnvironmentalSearch);
clearTankBtn.addEventListener('click', () => {
  selectedTank = null;
  updateSelectedTankPanel();
  renderMap(latestResults);
});

refreshProjects();
