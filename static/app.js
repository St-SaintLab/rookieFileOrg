const uploadBtn = document.getElementById('uploadBtn');
const folderInput = document.getElementById('folderInput');
const uploadedText = document.getElementById('uploadedText');
const uploadedIcon = document.getElementById('uploadedIcon');
const settingsPanel = document.getElementById('settingsPanel');
const logsPanel = document.getElementById('logsPanel');
const applyBtn = document.getElementById('applyBtn');
const organizationMode = document.getElementById('organizationMode');
const renamePattern = document.getElementById('renamePattern');
const renameEnabled = document.getElementById('renameEnabled');
const recursiveScan = document.getElementById('recursiveScan');
const metadataRead = document.getElementById('metadataRead');
const duplicateDetection = document.getElementById('duplicateDetection');
const dateBasis = document.getElementById('dateBasis');
const customRules = document.getElementById('customRules');
const configFile = document.getElementById('configFile');
const logsBody = document.getElementById('logsBody');
const successOverlay = document.getElementById('successOverlay');
const errorOverlay = document.getElementById('errorOverlay');
const okBtn = document.getElementById('okBtn');
const closeErrorBtn = document.getElementById('closeErrorBtn');
const dupCriteria = [...document.querySelectorAll('.dup-criterion')];
const categoryToggles = [...document.querySelectorAll('.cat-toggle')];
const typeOnlyBlocks = [...document.querySelectorAll('.type-only')];
const dateOnlyFields = [...document.querySelectorAll('.date-only')];
const customOnlyFields = [...document.querySelectorAll('.custom-only')];
const renameOnlyFields = [...document.querySelectorAll('.rename-only')];
const duplicateOnlyFields = [...document.querySelectorAll('.duplicate-only')];

let uploadId = null;
let downloadUrl = null;
let currentJob = null;
let uploadedFileInfo = null;

function setUploadedSummary(icon, text) {
  uploadedIcon.textContent = icon;
  uploadedText.textContent = text;
}

function showLogs(items) {
  logsBody.innerHTML = '';
  if (!items || !items.length) {
    logsBody.innerHTML = '<div class="log-empty">No actions yet.</div>';
    return;
  }
  items.forEach((entry) => {
    const row = document.createElement('div');
    row.className = `log-item ${entry.error ? 'error' : ''}`;
    row.innerHTML = `
      <div class="log-top">
        <span>${entry.timestamp}</span>
        <span>${entry.action}</span>
      </div>
      <div class="log-path">${entry.old_path || ''}</div>
      ${entry.new_path ? `<div class="log-path">→ ${entry.new_path}</div>` : ''}
      <div>${entry.message || ''}</div>
    `;
    logsBody.appendChild(row);
  });
}

function getSelectedDuplicateCriteria() {
  return dupCriteria.filter((c) => c.checked).map((c) => c.value);
}

function getSelectedCategories() {
  return categoryToggles.reduce((acc, c) => {
    acc[c.value] = c.checked;
    return acc;
  }, {});
}

function settingsValid() {
  const mode = organizationMode.value;
  const hasPattern = !renameEnabled.checked || renamePattern.value.trim().length > 0;
  const duplicateOk = !duplicateDetection.checked || getSelectedDuplicateCriteria().length > 0;
  const categoriesOk = mode !== 'type' || categoryToggles.some((c) => c.checked);
  const customOk = mode !== 'custom' || customRules.value.trim().length > 0;
  const dateOk = mode !== 'date' || dateBasis.value.trim().length > 0;
  return hasPattern && duplicateOk && categoriesOk && customOk && dateOk;
}

function updateSettingsVisibility() {
  typeOnlyBlocks.forEach((el) => (el.style.display = organizationMode.value === 'type' ? '' : 'none'));
  dateOnlyFields.forEach((el) => (el.style.display = organizationMode.value === 'date' ? '' : 'none'));
  customOnlyFields.forEach((el) => (el.style.display = organizationMode.value === 'custom' ? '' : 'none'));
  renameOnlyFields.forEach((el) => (el.style.display = renameEnabled.checked ? '' : 'none'));
  duplicateOnlyFields.forEach((el) => (el.style.display = duplicateDetection.checked ? '' : 'none'));
  applyBtn.disabled = !settingsValid();
}

function hideLogsPanel() {
  logsPanel.style.visibility = 'hidden';
}

function showLogsPanel() {
  logsPanel.style.visibility = 'visible';
}

function resetToUploadFolderState() {
  uploadId = null;
  downloadUrl = null;
  currentJob = null;
  uploadBtn.textContent = 'Upload Folder';
  uploadBtn.disabled = false;
}

[
  organizationMode,
  renamePattern,
  renameEnabled,
  recursiveScan,
  metadataRead,
  duplicateDetection,
  dateBasis,
  customRules,
].forEach((el) => el.addEventListener('input', updateSettingsVisibility));

dupCriteria.forEach((el) => el.addEventListener('change', updateSettingsVisibility));
categoryToggles.forEach((el) => el.addEventListener('change', updateSettingsVisibility));

function toFormDataSettings() {
  return {
    organization_mode: organizationMode.value,
    rename_pattern: renamePattern.value.trim(),
    rename_enabled: renameEnabled.checked,
    recursive_scan: recursiveScan.checked,
    read_metadata: metadataRead.checked,
    duplicate_detection: duplicateDetection.checked,
    duplicate_criteria: getSelectedDuplicateCriteria(),
    date_basis: dateBasis.value,
    custom_rules_text: customRules.value.trim(),
    categories_enabled: getSelectedCategories(),
  };
}

function openOverlay(el) {
  el.classList.remove('hidden');
  el.setAttribute('aria-hidden', 'false');
}

function closeOverlay(el) {
  el.classList.add('hidden');
  el.setAttribute('aria-hidden', 'true');
}

uploadBtn.addEventListener('click', () => {
  if (!uploadId) {
    hideLogsPanel();
    folderInput.click();
    return;
  }

  if (uploadBtn.textContent === 'Organize') {
    organizeFolder();
  } else {
    folderInput.click();
  }
});

folderInput.addEventListener('change', async () => {
  const files = [...folderInput.files];
  if (!files.length) return;

  hideLogsPanel();
  setUploadedSummary('…', 'Uploading...');
  uploadBtn.disabled = true;

  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files[]', file, file.webkitRelativePath || file.name);
    formData.append('relative_paths[]', file.webkitRelativePath || file.name);
  });

  try {
    const response = await fetch('/api/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || 'Upload failed.');

    uploadedFileInfo = data;
    uploadId = data.upload_id;
    setUploadedSummary('…', `${data.folder_name}\n${data.size_label}`);
    settingsPanel.style.visibility = 'visible';
    uploadBtn.textContent = 'Upload Folder';
    uploadBtn.disabled = false;
    updateSettingsVisibility();
  } catch (error) {
    setUploadedSummary('✕', 'File Organizer Does Not Save Any Folder(s) or File(s).');
    uploadBtn.disabled = false;
    openError(String(error.message || error));
  } finally {
    folderInput.value = '';
  }
});

applyBtn.addEventListener('click', () => {
  if (!settingsValid()) return;
  settingsPanel.style.visibility = 'hidden';
  uploadBtn.textContent = 'Organize';
  uploadBtn.disabled = false;
});

async function organizeFolder() {
  if (!uploadId) return;
  uploadBtn.disabled = true;
  setUploadedSummary('…', 'Uploading...');

  const formData = new FormData();
  formData.append('upload_id', uploadId);
  formData.append('settings', JSON.stringify(toFormDataSettings()));
  if (configFile.files && configFile.files[0]) {
    formData.append('config_file', configFile.files[0]);
  }

  try {
    const response = await fetch('/api/organize', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || 'Organization failed.');

    currentJob = data;
    downloadUrl = data.download_url;
    showLogs(data.logs);
    showLogsPanel();
    openOverlay(successOverlay);
  } catch (error) {
    setUploadedSummary('✕', uploadedFileInfo ? `${uploadedFileInfo.folder_name}\n${uploadedFileInfo.size_label}` : 'Organization failed.');
    openError(String(error.message || error));
  } finally {
    uploadBtn.disabled = false;
  }
}

function openError(message) {
  console.error(message);
  openOverlay(errorOverlay);
}

okBtn.addEventListener('click', async () => {
  if (downloadUrl) {
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  closeOverlay(successOverlay);

  if (uploadedFileInfo) {
    setUploadedSummary('✓', `${uploadedFileInfo.folder_name}\n${uploadedFileInfo.size_label}`);
  }

  resetToUploadFolderState();
  settingsPanel.style.visibility = 'hidden';
});

closeErrorBtn.addEventListener('click', () => {
  closeOverlay(errorOverlay);
});

updateSettingsVisibility();
hideLogsPanel();