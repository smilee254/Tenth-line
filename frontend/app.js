/**
 * app.js — Tenthline frontend logic
 *
 * Modules:
 *   FileUploader   – drag-drop + browse, file validation
 *   OptionsPanel   – reads all form controls
 *   APIClient      – posts to /api/process, returns PDF blob
 *   Previewer      – renders blob in iframe, drives download
 *   App            – wires everything together
 */

'use strict';

/* ── Constants ──────────────────────────────────────────────────────────────── */
const MAX_FILE_BYTES = 50 * 1024 * 1024; // 50 MB
const ALLOWED_EXTENSIONS = ['pdf', 'docx'];
const API_ENDPOINT = '/api/process';

const PROCESSING_STEPS = [
  'Uploading document…',
  'Analysing visual lines…',
  'Counting baselines…',
  'Stamping line numbers…',
  'Finalising PDF…',
];

/* ── Helpers ────────────────────────────────────────────────────────────────── */
function fmt_bytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(2)} MB`;
}

function ext(filename) {
  return filename.split('.').pop().toLowerCase();
}

/* ── FileUploader ───────────────────────────────────────────────────────────── */
class FileUploader {
  constructor({ dropzone, fileInput, browseBtn, fileInfo, fileName, fileSize, clearBtn, onFile, onClear }) {
    this.file = null;
    this.onFile = onFile;
    this.onClear = onClear;

    this.dropzone = dropzone;
    this.fileInfo = fileInfo;
    this.fileName = fileName;
    this.fileSize = fileSize;

    // Browse button
    browseBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fileInput.click();
    });

    // Dropzone click
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
    });

    // Drag events
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('drag-over'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('drag-over');
      const f = e.dataTransfer?.files?.[0];
      if (f) this._handleFile(f);
    });

    // Input change
    fileInput.addEventListener('change', () => {
      const f = fileInput.files?.[0];
      if (f) this._handleFile(f);
      fileInput.value = ''; // allow re-selecting same file
    });

    // Clear
    clearBtn.addEventListener('click', () => this._clear());
  }

  _validate(file) {
    if (!ALLOWED_EXTENSIONS.includes(ext(file.name))) {
      return `Unsupported file type ".${ext(file.name)}". Please upload a PDF or DOCX.`;
    }
    if (file.size > MAX_FILE_BYTES) {
      return `File is too large (${fmt_bytes(file.size)}). Maximum is 50 MB.`;
    }
    return null;
  }

  _handleFile(file) {
    const err = this._validate(file);
    if (err) { this.onFile(null, err); return; }

    this.file = file;
    this.fileName.textContent = file.name;
    this.fileSize.textContent = fmt_bytes(file.size);
    this.fileInfo.hidden = false;
    this.dropzone.hidden = true;
    this.onFile(file, null);
  }

  _clear() {
    this.file = null;
    this.fileInfo.hidden = true;
    this.dropzone.hidden = false;
    this.onClear();
  }

  getFile() { return this.file; }
}

/* ── OptionsPanel ───────────────────────────────────────────────────────────── */
class OptionsPanel {
  constructor() {
    this.intervalSlider  = document.getElementById('opt-interval');
    this.intervalDisplay = document.getElementById('interval-display');
    this.skipSlider      = document.getElementById('opt-skip');
    this.skipDisplay     = document.getElementById('skip-display');
    this.ruleToggle      = document.getElementById('opt-rule');

    this._bind(this.intervalSlider, this.intervalDisplay);
    this._bind(this.skipSlider, this.skipDisplay);
  }

  _bind(slider, display) {
    const update = () => { display.textContent = slider.value; };
    slider.addEventListener('input', update);
    update();
  }

  getOptions() {
    const marginSide = document.querySelector('input[name="margin_side"]:checked')?.value || 'left';
    return {
      interval:    parseInt(this.intervalSlider.value, 10),
      skip_pages:  parseInt(this.skipSlider.value, 10),
      margin_side: marginSide,
      draw_rule:   this.ruleToggle.checked,
    };
  }
}

/* ── APIClient ──────────────────────────────────────────────────────────────── */
class APIClient {
  /**
   * @param {File} file
   * @param {object} options
   * @param {function} onProgress – called with step message strings
   * @returns {Promise<{blob: Blob, filename: string}>}
   */
  async process(file, options, onProgress) {
    const form = new FormData();
    form.append('file', file);
    form.append('interval',    String(options.interval));
    form.append('skip_pages',  String(options.skip_pages));
    form.append('margin_side', options.margin_side);
    form.append('draw_rule',   options.draw_rule ? 'true' : 'false');

    // Cycle progress messages while waiting
    let stepIdx = 0;
    const stepTimer = setInterval(() => {
      if (stepIdx < PROCESSING_STEPS.length - 1) stepIdx++;
      onProgress(PROCESSING_STEPS[stepIdx]);
    }, 900);

    onProgress(PROCESSING_STEPS[0]);

    try {
      const resp = await fetch(API_ENDPOINT, { method: 'POST', body: form });

      clearInterval(stepTimer);

      if (!resp.ok) {
        let detail = `Server error (${resp.status})`;
        try {
          const json = await resp.json();
          detail = json.detail || detail;
        } catch (_) { /* ignore */ }
        throw new Error(detail);
      }

      const blob = await resp.blob();
      const filename = (resp.headers.get('X-Filename') || 'document_tenthlined.pdf');
      return { blob, filename };

    } catch (err) {
      clearInterval(stepTimer);
      throw err;
    }
  }
}

/* ── Previewer ──────────────────────────────────────────────────────────────── */
class Previewer {
  constructor({ placeholder, iframe, downloadBtn }) {
    this.placeholder  = placeholder;
    this.iframe       = iframe;
    this.downloadBtn  = downloadBtn;
    this._blobUrl     = null;
    this._filename    = null;

    downloadBtn.addEventListener('click', () => this._download());
  }

  show(blob, filename) {
    if (this._blobUrl) URL.revokeObjectURL(this._blobUrl);

    this._blobUrl  = URL.createObjectURL(blob);
    this._filename = filename;

    this.placeholder.hidden = true;
    this.iframe.src = this._blobUrl;
    this.iframe.hidden = false;
    this.downloadBtn.hidden = false;
  }

  reset() {
    this.placeholder.hidden = false;
    this.iframe.hidden = true;
    this.iframe.src = '';
    this.downloadBtn.hidden = true;
    if (this._blobUrl) { URL.revokeObjectURL(this._blobUrl); this._blobUrl = null; }
  }

  _download() {
    if (!this._blobUrl) return;
    const a = document.createElement('a');
    a.href = this._blobUrl;
    a.download = this._filename || 'tenthlined.pdf';
    a.click();
  }
}

/* ── App ────────────────────────────────────────────────────────────────────── */
class App {
  constructor() {
    this.processBtn     = document.getElementById('process-btn');
    this.processBtnLbl  = document.getElementById('process-btn-label');
    this.errorBox       = document.getElementById('error-box');
    this.errorText      = document.getElementById('error-text');
    this.overlay        = document.getElementById('processing-overlay');
    this.overlayLabel   = document.getElementById('processing-label');

    this.api      = new APIClient();
    this.options  = new OptionsPanel();

    this.uploader = new FileUploader({
      dropzone:  document.getElementById('dropzone'),
      fileInput: document.getElementById('file-input'),
      browseBtn: document.getElementById('browse-btn'),
      fileInfo:  document.getElementById('file-info'),
      fileName:  document.getElementById('file-info-name'),
      fileSize:  document.getElementById('file-info-size'),
      clearBtn:  document.getElementById('file-clear-btn'),
      onFile:    (file, err) => this._onFile(file, err),
      onClear:   ()          => this._onClear(),
    });

    this.previewer = new Previewer({
      placeholder:  document.getElementById('preview-placeholder'),
      iframe:       document.getElementById('preview-iframe'),
      downloadBtn:  document.getElementById('download-btn'),
    });

    this.processBtn.addEventListener('click', () => this._process());
  }

  _onFile(file, err) {
    this._clearError();
    if (err) {
      this._showError(err);
      this._setReady(false);
      return;
    }
    this._setReady(true);
  }

  _onClear() {
    this._setReady(false);
    this._clearError();
    this.previewer.reset();
  }

  _setReady(ready) {
    this.processBtn.disabled = !ready;
    this.processBtn.setAttribute('aria-disabled', String(!ready));
  }

  _showError(msg) {
    this.errorText.textContent = msg;
    this.errorBox.hidden = false;
  }

  _clearError() {
    this.errorBox.hidden = true;
    this.errorText.textContent = '';
  }

  _setProcessing(active) {
    this.overlay.hidden = !active;
    this.processBtn.disabled = active;
    this.processBtnLbl.textContent = active ? 'Processing…' : 'Number My Document';
  }

  async _process() {
    const file = this.uploader.getFile();
    if (!file) return;

    this._clearError();
    this._setProcessing(true);

    try {
      const opts = this.options.getOptions();
      const { blob, filename } = await this.api.process(file, opts, (msg) => {
        this.overlayLabel.textContent = msg;
      });
      this.previewer.show(blob, filename);
    } catch (err) {
      this._showError(err.message || 'An unexpected error occurred.');
    } finally {
      this._setProcessing(false);
    }
  }
}

/* ── Bootstrap ──────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => new App());
