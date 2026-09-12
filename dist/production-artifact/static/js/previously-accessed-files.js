<!-- Previously Accessed Files Component -->
<!-- Include this in your dashboard template -->

<div id="previously-accessed-container" style="display: none;">
  <section class="previously-accessed-section" style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px;">
    <h2 style="margin-top: 0; color: #333;">
      <i class="fas fa-history" style="margin-right: 8px;"></i>
      Previously Accessed Files
    </h2>
    
    <div id="file-history-loading" style="text-align: center; padding: 20px; display: none;">
      <i class="fas fa-spinner fa-spin" style="font-size: 24px; color: #007bff;"></i>
      <p>Loading your file history...</p>
    </div>
    
    <div id="file-history-empty" style="text-align: center; padding: 20px; color: #666; display: none;">
      <i class="fas fa-inbox" style="font-size: 32px; margin-bottom: 10px; opacity: 0.5;"></i>
      <p>You haven't accessed any files yet.</p>
    </div>
    
    <div id="file-history-error" style="padding: 15px; background: #f8d7da; color: #721c24; border-radius: 4px; display: none; margin-bottom: 10px;">
      <i class="fas fa-exclamation-circle"></i>
      <span id="file-history-error-message"></span>
    </div>
    
    <div id="file-history-list" style="display: none;">
      <div style="max-height: 400px; overflow-y: auto;">
        <table style="width: 100%; border-collapse: collapse;">
          <thead>
            <tr style="border-bottom: 2px solid #dee2e6;">
              <th style="text-align: left; padding: 10px; color: #666; font-weight: 600;">File Name</th>
              <th style="text-align: left; padding: 10px; color: #666; font-weight: 600;">Type</th>
              <th style="text-align: left; padding: 10px; color: #666; font-weight: 600;">Accessed</th>
              <th style="text-align: center; padding: 10px; color: #666; font-weight: 600;">Action</th>
            </tr>
          </thead>
          <tbody id="file-history-items">
            <!-- Items will be inserted here -->
          </tbody>
        </table>
      </div>
    </div>
  </section>
</div>

<script>
// Previously Accessed Files Component
class PreviouslyAccessedFiles {
  constructor() {
    this.container = document.getElementById('previously-accessed-container');
    this.loadingEl = document.getElementById('file-history-loading');
    this.emptyEl = document.getElementById('file-history-empty');
    this.errorEl = document.getElementById('file-history-error');
    this.errorMsgEl = document.getElementById('file-history-error-message');
    this.listEl = document.getElementById('file-history-list');
    this.itemsEl = document.getElementById('file-history-items');
  }

  async load(limit = 10) {
    try {
      if (!this.container) return; // Component not in DOM
      
      this.container.style.display = 'block';
      this.showLoading(true);
      this.hideError();

      const response = await fetch(`/api/file-access-history?limit=${limit}`);
      const data = await response.json();

      if (data.success && data.count > 0) {
        this.renderHistory(data.data);
      } else {
        this.showEmpty();
      }
    } catch (error) {
      console.error('Error loading file history:', error);
      this.showError('Failed to load file access history. Please try again later.');
    } finally {
      this.showLoading(false);
    }
  }

  renderHistory(files) {
    this.itemsEl.innerHTML = '';
    this.emptyEl.style.display = 'none';
    this.listEl.style.display = 'block';

    files.forEach((file, index) => {
      const row = document.createElement('tr');
      row.style.borderBottom = '1px solid #dee2e6';
      if (index % 2 === 0) {
        row.style.backgroundColor = '#fff';
      } else {
        row.style.backgroundColor = '#f8f9fa';
      }

      const fileName = file.file_name || 'Unknown';
      const fileType = file.file_type || 'file';
      const fileUrl = file.file_url || '#';
      const accessedAt = new Date(file.accessed_at).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });

      row.innerHTML = `
        <td style="padding: 10px; color: #333;">
          <i class="fas fa-file" style="margin-right: 8px; color: #007bff;"></i>
          ${this.escapeHtml(fileName)}
        </td>
        <td style="padding: 10px; color: #666; font-size: 0.9em;">
          <span style="background: #e7f3ff; padding: 4px 8px; border-radius: 3px;">
            ${this.escapeHtml(fileType)}
          </span>
        </td>
        <td style="padding: 10px; color: #666; font-size: 0.9em;">
          ${accessedAt}
        </td>
        <td style="padding: 10px; text-align: center;">
          <button 
            onclick="window.open('${this.escapeHtml(fileUrl)}', '_blank')"
            style="background: #007bff; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 0.9em;"
            title="Open file"
          >
            <i class="fas fa-external-link-alt"></i> Open
          </button>
        </td>
      `;
      this.itemsEl.appendChild(row);
    });
  }

  showLoading(show) {
    this.loadingEl.style.display = show ? 'block' : 'none';
  }

  showEmpty() {
    this.listEl.style.display = 'none';
    this.emptyEl.style.display = 'block';
  }

  showError(message) {
    this.errorMsgEl.textContent = message;
    this.errorEl.style.display = 'block';
    this.listEl.style.display = 'none';
    this.emptyEl.style.display = 'none';
  }

  hideError() {
    this.errorEl.style.display = 'none';
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize and load on page ready
document.addEventListener('DOMContentLoaded', function() {
  const historyComponent = new PreviouslyAccessedFiles();
  if (document.getElementById('previously-accessed-container')) {
    historyComponent.load(15); // Load last 15 accessed files
  }
});
</script>

<style>
.previously-accessed-section {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.previously-accessed-section h2 {
  display: flex;
  align-items: center;
  font-size: 1.3em;
  margin-bottom: 15px;
}

.previously-accessed-section table {
  width: 100%;
  font-size: 0.95em;
}

.previously-accessed-section tbody tr:hover {
  background-color: #f1f3f5 !important;
}

.previously-accessed-section button:hover {
  background: #0056b3 !important;
  transform: translateY(-2px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: all 0.2s ease;
}

@media (max-width: 768px) {
  .previously-accessed-section {
    padding: 10px;
  }

  .previously-accessed-section table {
    font-size: 0.85em;
  }

  .previously-accessed-section td {
    padding: 8px !important;
  }

  .previously-accessed-section button {
    padding: 4px 8px !important;
    font-size: 0.8em !important;
  }
}
</style>
