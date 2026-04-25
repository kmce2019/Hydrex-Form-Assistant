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
}).addTo(map);

const layerGroup = L.layerGroup().addTo(map);

function allFields() {
  return Array.from(formContainer.querySelectorAll('input[name], select[name], textarea[name]'));
}

function selectedSources() {
  return Array.from(document.querySelectorAll('input[name="source_check"]:checked')).map((el) => el.value);
}

function setSelectedSources(values = []) {
  document.querySelectorAll('input[name="source_check"]').forEach((el) => {
    el.checked = values.includes(el.value);
  });
}

function collectPayload() {
  const payload = {};
  allFields().forEach((field) => {
    payload[field.name] = field.value;
  });

  if (latestResults && Object.keys(latestResults).length > 0) {
    payload.environmental_results_json = JSON.stringify(latestResults);
  }

  if (currentProjectId) payload.id = currentProjectId;

  return payload;
}

function renderMap(results = {}) {
  layerGroup.clearLayers();
  if (!results.latitude) return;

  const center = [results.latitude, results.longitude];
  L.marker(center).addTo(layerGroup);
  L.circle(center, { radius: 804.67 }).addTo(layerGroup);
  L.circle(center, { radius: 1609.34 }).addTo(layerGroup);
  map.setView(center, 13);
}

async function runEnvironmentalSearch() {
  const project = collectPayload();

  const res = await fetch('/api/environmental-search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      project,
      tceq_csv: currentTceqCsv,
      selected_sources: selectedSources()
    })
  });

  const data = await res.json();
  latestResults = data;

  renderMap(data);

  rcraCard.textContent = data.rcra_count_half_mile ?? '-';
  lpstCard.textContent = data.lpst_count_half_mile ?? '-';
  pstCard.textContent = data.pst_count_one_mile ?? '-';
}

async function generateSummaries() {
  const payload = collectPayload();

  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });

  const data = await res.json();

  explosiveOutput.value = data.explosive_summary;
  contaminationOutput.value = data.contamination_summary;
}

runSearchBtn.addEventListener('click', runEnvironmentalSearch);
generateBtn.addEventListener('click', generateSummaries);