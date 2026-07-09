/**
 * AbhiHubSelect - Universal Searchable Forms with Dependency Mapping
 */
const AbhiHubSelect = {
    instances: {},
    
    init() {
        document.querySelectorAll('.abhihub-select').forEach(el => {
            if (el.tomselect) return;
            
            const entity = el.dataset.entity; // college, department, semester, subject
            const parentId = el.dataset.parent; // ID of the parent select
            
            const ts = new TomSelect(el, {
                valueField: 'value',
                labelField: 'text',
                searchField: ['text'],
                create: function(input, callback) {
                    const parentVal = parentId ? document.getElementById(parentId)?.value : null;
                    openEntityModal(entity, el.id, input, parentVal, callback);
                },
                createFilter: function(input) { return input.trim().length > 0; },
                sortField: { field: "text", direction: "asc" },
                render: {
                    option_create: function(data, escape) {
                        return '<div class="create-new-option">＋ Add New ' + escape(entity.charAt(0).toUpperCase() + entity.slice(1)) + '</div>';
                    },
                    no_results: function(data, escape) {
                        return '<div class="no-results">No matching ' + escape(entity) + ' found.</div>';
                    }
                },
                onItemAdd: function() {
                    this.blur();
                }
            });
            
            this.instances[el.id] = ts;
            
            // Handle dependency logic
            if (parentId) {
                const parentEl = document.getElementById(parentId);
                if (parentEl) {
                    parentEl.addEventListener('change', () => {
                        AbhiHubSelect.handleParentChange(el.id, parentEl.value);
                    });
                    
                    // Initial state
                    if (!parentEl.value) {
                        ts.disable();
                        ts.clearOptions();
                    }
                }
            } else if (entity === 'college') {
                // Auto-fetch root entity
                AbhiHubSelect.loadColleges(el.id);
            }
        });
    },
    
    async loadColleges(selectId) {
        const ts = this.instances[selectId];
        if (!ts) return;
        ts.settings.placeholder = 'Loading colleges...';
        if (ts.control_input) ts.control_input.placeholder = 'Loading colleges...';
        try {
            const res = await fetch('/api/colleges');
            const json = await res.json();
            const items = json.colleges || json.data || [];
            ts.clearOptions();
            items.forEach(c => {
                const text = c.short_name ? `${c.name} (${c.short_name})` : c.name;
                ts.addOption({ value: c.id, text: text });
            });
            ts.settings.placeholder = 'Select College';
            if (ts.control_input) ts.control_input.placeholder = 'Select College';
            ts.enable();
            ts.refreshOptions(false);
        } catch (e) {
            console.error('Failed to load colleges', e);
            ts.settings.placeholder = 'Error loading options';
        }
    },
    
    async handleParentChange(selectId, parentValue) {
        const el = document.getElementById(selectId);
        const ts = this.instances[selectId];
        if (!el || !ts) return;
        
        ts.clear();
        ts.clearOptions();
        
        if (!parentValue) {
            ts.disable();
            // Also trigger change to clear its children
            el.dispatchEvent(new Event('change'));
            return;
        }
        
        ts.disable();
        ts.settings.placeholder = 'Loading...';
        if (ts.control_input) ts.control_input.placeholder = 'Loading...';
        
        try {
            const entity = el.dataset.entity;
            const parentParam = el.dataset.parentParam || 'college_id'; // dynamic fallback
            
            let url = '';
            if (entity === 'department' || entity === 'branch') url = `/api/departments?college_id=${parentValue}`;
            else if (entity === 'semester') url = `/api/semesters?department_id=${parentValue}`;
            else if (entity === 'subject') {
                // Our backend subject API expects department_id, not semester_id (since semester is optional)
                // We map semester's parent (department) to this API call.
                // Wait, if parent is semester, we need to pass department_id AND semester.
                const semEl = document.getElementById(el.dataset.parent);
                const deptId = semEl ? document.getElementById(semEl.dataset.parent)?.value : null;
                
                url = `/api/subjects?department_id=${deptId}&semester=${parentValue}`;
            }
            
            const response = await fetch(url);
            const json = await response.json();
            
            const dataKey = entity === 'branch' ? 'departments' : `${entity}s`;
            const items = json[dataKey] || json.data || [];
            
            items.forEach(item => {
                const text = item.subject_code ? `${item.name} (${item.subject_code})` : item.name;
                ts.addOption({ value: item.id, text: text });
            });
            
            ts.settings.placeholder = 'Select ' + entity;
            if (ts.control_input) ts.control_input.placeholder = 'Select ' + entity;
            ts.enable();
        } catch (err) {
            console.error('Failed to load options for', selectId, err);
            ts.settings.placeholder = 'Error loading options';
            if (ts.control_input) ts.control_input.placeholder = 'Error loading options';
            ts.enable();
        }
        
        // Trigger change to cascade down to children
        el.dispatchEvent(new Event('change'));
    },
    
    refresh(selectId) {
        const el = document.getElementById(selectId);
        if (el && el.dataset.parent) {
            const parentEl = document.getElementById(el.dataset.parent);
            this.handleParentChange(selectId, parentEl ? parentEl.value : null);
        }
    }
};

/**
 * Global Add Entity Modal Logic
 */
function openEntityModal(entityType, targetSelectId, initialInput, parentValue, tomSelectCallback) {
    const modal = document.getElementById('globalEntityModal');
    if (!modal) return; // if modal HTML is not injected
    
    // Set titles
    document.getElementById('entityModalTitle').textContent = 'Add New ' + entityType.charAt(0).toUpperCase() + entityType.slice(1);
    
    // Hide all form fields first
    document.querySelectorAll('.entity-field-group').forEach(el => el.style.display = 'none');
    
    // Show relevant fields
    document.getElementById('entityNameField').style.display = 'block';
    const nameInput = document.getElementById('entityName');
    nameInput.value = initialInput || '';
    
    if (entityType === 'college') {
        document.getElementById('entityAbbrField').style.display = 'block';
        document.getElementById('entityAbbrField').querySelector('label').textContent = 'Short Name (Optional)';
    } else if (entityType === 'department' || entityType === 'branch') {
        document.getElementById('entityAbbrField').style.display = 'block';
        document.getElementById('entityAbbrField').querySelector('label').textContent = 'Abbreviation (e.g. CSE)';
    } else if (entityType === 'subject') {
        document.getElementById('entitySemesterField').style.display = 'block';
        const semSelect = document.getElementById('entitySemester');
        // parentValue here is the semester number (1-8) — pre-select it
        if (parentValue && parseInt(parentValue) >= 1 && parseInt(parentValue) <= 8) {
            semSelect.value = parentValue;
        } else {
            semSelect.value = '';
        }
        document.getElementById('entityCodeField').style.display = 'block';
    }
    
    // Store metadata on the form for submission
    const form = document.getElementById('entityModalForm');
    form.dataset.entity = entityType;
    form.dataset.targetId = targetSelectId;
    form.dataset.parentVal = parentValue || '';
    
    // Keep the tomSelectCallback to invoke on success
    // Use addEventListener to avoid overwriting/losing handlers on re-open.
    // Also remove previous submit handler to prevent double submits.
    if (form.__abhihub_submit_handler) {
        form.removeEventListener('submit', form.__abhihub_submit_handler);
    }

    const handler = (e) => {
        e.preventDefault();
        submitEntityModal(tomSelectCallback);
    };

    form.__abhihub_submit_handler = handler;
    form.addEventListener('submit', handler);
    
    // Show modal
    modal.classList.add('show');
    nameInput.focus();
    
    // Handle Cancel
    document.getElementById('entityModalCancel').onclick = function() {
        modal.classList.remove('show');
        if (tomSelectCallback) tomSelectCallback(); // cancel creation
    };
}

async function submitEntityModal(tomSelectCallback) {
    const form = document.getElementById('entityModalForm');
    const entity = form.dataset.entity;
    const parentVal = form.dataset.parentVal;

    const submitBtn = document.getElementById('entityModalSubmit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    const name = document.getElementById('entityName').value.trim();
    const abbr = document.getElementById('entityAbbr').value.trim();
    const code = document.getElementById('entityCode').value.trim();

    if (!name) {
        alert('Name is required');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save';
        return;
    }

    // Map entity type to API URL and response key
    const API_MAP = {
        college:    { url: '/api/colleges',    key: 'college' },
        branch:     { url: '/api/departments', key: 'department' },
        department: { url: '/api/departments', key: 'department' },
        subject:    { url: '/api/subjects',    key: 'subject' },
    };

    const mapping = API_MAP[entity];
    if (!mapping) {
        alert(`Cannot add new ${entity} — not supported.`);
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save';
        return;
    }

    let payload = { name };

    if (entity === 'college') {
        if (abbr) payload.abbreviation = abbr;
    } else if (entity === 'branch' || entity === 'department') {
        if (abbr) payload.abbreviation = abbr;
        payload.college_id = parentVal || '';
    } else if (entity === 'subject') {
        if (code) payload.subject_code = code;
        const semVal = document.getElementById('entitySemester').value;
        if (!semVal) {
            alert('Please select a semester');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Save';
            return;
        }
        payload.semester = semVal;
        // Walk cascade: subjectName → semester → branch to get department_id
        const targetEl = document.getElementById(form.dataset.targetId);
        const semEl = targetEl ? document.getElementById(targetEl.dataset.parent) : null;
        const deptEl = semEl ? document.getElementById(semEl.dataset.parent) : null;
        // Use TomSelect getValue() if available, fallback to .value
        const deptTs = deptEl ? AbhiHubSelect.instances[deptEl.id] : null;
        const deptVal = deptTs ? deptTs.getValue() : (deptEl ? deptEl.value : '');
        payload.department_id = deptVal || parentVal || '';
        if (!payload.department_id) {
            alert('Please select a branch and semester before adding a new subject.');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Save';
            return;
        }
    }

    try {
        const response = await fetch(mapping.url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const json = await response.json();

        if (json.success) {
            const newItem = json[mapping.key] || json.data;
            const itemText = newItem.subject_code
                ? `${newItem.name} (${newItem.subject_code})`
                : (newItem.abbreviation ? `${newItem.name} (${newItem.abbreviation})` : newItem.name);

            document.getElementById('globalEntityModal').classList.remove('show');

            if (tomSelectCallback) tomSelectCallback({ value: newItem.id, text: itemText });

            // Fire native change so cascade dropdowns react
            const targetEl = document.getElementById(form.dataset.targetId);
            if (targetEl) setTimeout(() => targetEl.dispatchEvent(new Event('change')), 50);

            if (window.showToast) window.showToast(`${entity} added successfully!`, 'success');
        } else {
            alert(json.message || `Failed to add ${entity}`);
            if (tomSelectCallback) tomSelectCallback();
        }
    } catch (err) {
        console.error(err);
        alert('Network error. Please try again.');
        if (tomSelectCallback) tomSelectCallback();
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save';
    }
}

// Auto init on DOM load
document.addEventListener('DOMContentLoaded', () => {
    AbhiHubSelect.init();
});
