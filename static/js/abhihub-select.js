/**
 * AbhiHubSelect - Universal Searchable Forms with Dependency Mapping
 */
const AbhiHubSelect = {
    instances: {},
    apiCache: {},
    
    init() {
        document.querySelectorAll('select.abhihub-select').forEach(el => {
            if (el.tomselect) return;
            
            const entity = el.dataset.entity; // college, department, semester, subject
            const parentId = el.dataset.parent; // ID of the parent select
            const parentClass = el.dataset.parentClass; // Class of the parent select
            
            const getParentEl = () => {
                if (parentId) return document.getElementById(parentId);
                if (parentClass) return el.closest('.meta-form-wrap')?.querySelector(`.${parentClass}`);
                return null;
            };
            
            const ts = new TomSelect(el, {
                valueField: 'value',
                labelField: 'text',
                searchField: ['text'],
                create: function(input, callback) {
                    const parentEl = getParentEl();
                    const parentVal = parentEl ? parentEl.value : null;
                    // For dynamic forms, pass the element itself so we can find relations
                    openEntityModal(entity, el.id || el, input, parentVal, callback);
                },
                createFilter: function(input) { return input.trim().length > 0; },
                sortField: { field: "text", direction: "asc" },
                render: {
                    option_create: function(data, escape) {
                        return '<div class="create create-new-option">＋ Add New ' + escape(entity.charAt(0).toUpperCase() + entity.slice(1)) + '</div>';
                    },
                    no_results: function(data, escape) {
                        return '<div class="no-results">No matching ' + escape(entity) + ' found.</div>';
                    }
                },
                onItemAdd: function() {
                    this.blur();
                }
            });
            
            // Generate a unique ID if none exists for the instances map
            if (!el.id) el.id = 'abhihub_ts_' + Math.random().toString(36).substr(2, 9);
            this.instances[el.id] = ts;
            
            // Handle dependency logic
            const parentEl = getParentEl();
            if (parentEl) {
                parentEl.addEventListener('change', () => {
                    AbhiHubSelect.handleParentChange(el.id, parentEl.value, parentEl);
                });
                
                // Initial state
                if (!parentEl.value) {
                    ts.disable();
                    ts.clearOptions();
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
            let json;
            if (this.apiCache['/api/colleges']) {
                json = this.apiCache['/api/colleges'];
            } else {
                const res = await fetch('/api/colleges');
                json = await res.json();
                this.apiCache['/api/colleges'] = json;
            }
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
    
    async handleParentChange(selectId, parentValue, parentEl) {
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
                const semEl = parentEl || (el.dataset.parent ? document.getElementById(el.dataset.parent) : el.closest('.meta-form-wrap')?.querySelector('.semester-select'));
                const deptEl = semEl ? (semEl.dataset.parent ? document.getElementById(semEl.dataset.parent) : semEl.closest('.meta-form-wrap')?.querySelector('.branch-select')) : null;
                const deptId = deptEl ? deptEl.value : null;
                
                url = `/api/subjects?department_id=${deptId}&semester=${parentValue}`;
            }
            
            let json;
            if (this.apiCache[url]) {
                json = this.apiCache[url];
            } else {
                const response = await fetch(url);
                json = await response.json();
                this.apiCache[url] = json;
            }
            
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
    const isCarousel = document.getElementById('uploadCarousel')?.style.display === 'flex';
    
    if (isCarousel) {
        // Build inline form right below the select dropdown
        const targetEl = document.getElementById(targetSelectId);
        const wrapper = targetEl.closest('.meta-field') || targetEl.parentElement;
        
        // Remove existing if any
        wrapper.querySelector('.inline-entity-form')?.remove();
        
        const inlineForm = document.createElement('div');
        inlineForm.className = 'inline-entity-form';
        inlineForm.style.cssText = 'margin-top: 10px; padding: 12px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 12px; animation: slideDown 0.2s ease-out;';
        
        let html = `<div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 8px; color: #1e293b;">Add New ${entityType.charAt(0).toUpperCase() + entityType.slice(1)}</div>`;
        html += `<input type="text" id="inlineEntityName" class="modern-input" style="padding: 0.6rem; margin-bottom: 8px; font-size: 0.9rem;" value="${initialInput || ''}" placeholder="Name *">`;
        
        if (entityType === 'college' || entityType === 'department' || entityType === 'branch') {
            html += `<input type="text" id="inlineEntityAbbr" class="modern-input" style="padding: 0.6rem; margin-bottom: 8px; font-size: 0.9rem;" placeholder="${entityType === 'college' ? 'Short Name' : 'Abbreviation'} (Optional)">`;
        } else if (entityType === 'subject') {
            html += `<input type="number" id="inlineEntitySemester" class="modern-input" style="padding: 0.6rem; margin-bottom: 8px; font-size: 0.9rem;" placeholder="Semester (1-8)" value="${parentValue || ''}">`;
            html += `<input type="text" id="inlineEntityCode" class="modern-input" style="padding: 0.6rem; margin-bottom: 8px; font-size: 0.9rem;" placeholder="Subject Code (Optional)">`;
        }
        
        html += `<div style="display: flex; gap: 8px;">
            <button type="button" id="inlineCancel" style="flex: 1; padding: 0.6rem; border-radius: 8px; border: 1px solid #cbd5e1; background: white; cursor: pointer;">Cancel</button>
            <button type="button" id="inlineSave" style="flex: 1; padding: 0.6rem; border-radius: 8px; border: none; background: #2563eb; color: white; font-weight: 600; cursor: pointer;">Save</button>
        </div>`;
        
        inlineForm.innerHTML = html;
        wrapper.appendChild(inlineForm);
        
        inlineForm.querySelector('#inlineEntityName').focus();
        
        inlineForm.querySelector('#inlineCancel').onclick = () => {
            inlineForm.remove();
            if (tomSelectCallback) tomSelectCallback();
        };
        
        inlineForm.querySelector('#inlineSave').onclick = async () => {
            const btn = inlineForm.querySelector('#inlineSave');
            btn.disabled = true;
            btn.textContent = 'Saving...';
            
            const name = inlineForm.querySelector('#inlineEntityName').value.trim();
            const abbr = inlineForm.querySelector('#inlineEntityAbbr')?.value.trim() || '';
            const code = inlineForm.querySelector('#inlineEntityCode')?.value.trim() || '';
            const sem  = inlineForm.querySelector('#inlineEntitySemester')?.value.trim() || parentValue || '';
            
            if (!name) { alert('Name is required'); btn.disabled = false; btn.textContent = 'Save'; return; }
            
            try {
                const res = await fetch('/api/admin/entity/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ entity: entityType, name: name, short_name: abbr, code: code, semester: sem, parent_id: parentValue })
                });
                const data = await res.json();
                if (data.success) {
                    if (tomSelectCallback) tomSelectCallback({ value: data.id, text: data.name });
                    inlineForm.remove();
                } else {
                    alert(data.message || 'Error saving entity');
                    btn.disabled = false;
                    btn.textContent = 'Save';
                }
            } catch (err) {
                alert('Network error');
                btn.disabled = false;
                btn.textContent = 'Save';
            }
        };
        return; // Skip global modal
    }

    const modal = document.getElementById('globalEntityModal');
    if (!modal) return; // if modal HTML is not injected
    
    // Ensure the modal is a direct child of the body to escape any nested stacking contexts (e.g. labeling-view)
    if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }
    
    if (document.getElementById('labelingView')?.classList.contains('active')) {
        modal.classList.add('store-room-mode');
    } else {
        modal.classList.remove('store-room-mode');
    }
    
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

// Expose to window for dynamic initialization (e.g. bulk upload clones)
window.AbhiHubSelect = AbhiHubSelect;
