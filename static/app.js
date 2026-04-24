let currentProjectId = null;

const formContainer = document.getElementById('intakeForm');
const savedProjects = document.getElementById('savedProjects');
const loadBtn = document.getElementById('loadBtn');
const newBtn = document.getElementById('newBtn');
const saveBtn = document.getElementById('saveBtn');
const exportBtn = document.getElementById('exportBtn');
const generateBtn = document.getElementById('generateBtn');
const explosiveOutput = document.getElementById('explosiveOutput');
const contaminationOutput = document.getElementById('contaminationOutput');
const checklistOutput = document.getElementById('checklistOutput');

function allFields() {
  return Array.from(formContainer.querySelectorAll('input[name], select[name], textarea[name]'));
}

function collectPayload() {
  const payload = {};
  allFields().forEach((field) => {
    payload[field.name] = field.value;
  });
  if (currentProjectId) {
    payload.id = currentProjectId;
  }
  return payload;
}

function fillForm(data) {
  allFields().forEach((field) => {
    field.value = data[field.name] ?? '';
  });
}

function resetForm() {
  currentProjectId = null;
  allFields().forEach((field) => {
    if (field.type === 'number') field.value = '0';
    else field.value = '';
  });
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

document.querySelectorAll('.copy-btn').forEach((btn) => btn.addEventListener('click', copyFromTarget));
loadBtn.addEventListener('click', loadProject);
newBtn.addEventListener('click', resetForm);
saveBtn.addEventListener('click', saveProject);
exportBtn.addEventListener('click', exportMarkdown);
generateBtn.addEventListener('click', generateSummaries);

refreshProjects();
