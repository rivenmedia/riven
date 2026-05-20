import { useCallback, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { apiFetch, downloadBackupFile } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import type { AppRoute } from '../../app/routeTypes';

interface ExportManifest {
  format_version?: number;
  counts?: {
    movies?: number;
    tv_shows?: number;
    pinned_streams?: number;
    pins_by_provider?: Record<string, number>;
  };
  warnings?: string[];
}

interface ExportResponse {
  success: boolean;
  message: string;
  filename?: string;
  manifest?: ExportManifest;
}

interface ImportResponse {
  success: boolean;
  message: string;
  added_movies?: number;
  added_shows?: number;
  skipped_titles?: number;
  pins_restored?: number;
  pins_failed?: number;
  errors?: string[];
}

export default function BackupRestoreView({ route: _route }: { route: AppRoute }) {
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [includeSettings, setIncludeSettings] = useState(true);
  const [redactSecrets, setRedactSecrets] = useState(false);
  const [restoreSettings, setRestoreSettings] = useState(false);
  const [skipExisting, setSkipExisting] = useState(true);
  const [restorePins, setRestorePins] = useState(true);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [lastExport, setLastExport] = useState<ExportResponse | null>(null);
  const [lastImport, setLastImport] = useState<ImportResponse | null>(null);

  const handleExport = useCallback(async () => {
    setExporting(true);
    setLastExport(null);
    const params = new URLSearchParams({
      include_settings: String(includeSettings),
      redact_secrets: String(redactSecrets),
    });
    const response = await apiFetch<ExportResponse>(
      `/database/export/bundle?${params.toString()}`,
      { method: 'POST' },
    );
    setExporting(false);

    if (!response.ok || !response.data?.success) {
      notify(response.error || 'Export failed', 'error');
      return;
    }

    setLastExport(response.data);
    notify(response.data.message || 'Backup created', 'success');

    if (response.data.filename) {
      try {
        await downloadBackupFile(response.data.filename);
      } catch (e) {
        notify(
          e instanceof Error ? e.message : 'Download failed after export',
          'warning',
        );
      }
    }
  }, [includeSettings, redactSecrets]);

  const handleImport = useCallback(async () => {
    if (!importFile) {
      notify('Choose a backup ZIP file', 'warning');
      return;
    }

    setImporting(true);
    setLastImport(null);

    const form = new FormData();
    form.append('file', importFile);
    form.append('restore_settings', String(restoreSettings));
    form.append('skip_existing_titles', String(skipExisting));
    form.append('restore_pins', String(restorePins));

    const response = await apiFetch<ImportResponse>('/database/import/bundle', {
      method: 'POST',
      body: form,
    });
    setImporting(false);

    if (!response.ok || !response.data?.success) {
      notify(response.error || 'Import failed', 'error');
      return;
    }

    setLastImport(response.data);
    notify(response.data.message || 'Import complete', 'success');
    setImportFile(null);
  }, [importFile, restoreSettings, skipExisting, restorePins]);

  const counts = lastExport?.manifest?.counts;

  return (
    <ViewLayout className="view-backup" view="backup">
      <ViewHeader
        title="Backup & Restore"
        subtitle="Export editable CSV library lists and per-provider pinned streams. Import re-adds titles and re-activates pins on debrid."
      />

      <Panel>
        <h2 className="panel-section-title">Export</h2>
        <p className="panel-hint">
          Creates a ZIP on the server (CSVs + manifest, optional settings). Video
          files are not included. Pins are grouped by debrid provider.
        </p>
        <div className="form-row form-row--checkboxes">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={includeSettings}
              onChange={(e) => setIncludeSettings(e.target.checked)}
            />
            Include settings.json
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={redactSecrets}
              onChange={(e) => setRedactSecrets(e.target.checked)}
              disabled={!includeSettings}
            />
            Redact secrets in settings
          </label>
        </div>
        <div className="form-actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={exporting}
            onClick={handleExport}
          >
            {exporting ? 'Exporting…' : 'Export & download'}
          </button>
        </div>
        {lastExport?.manifest && (
          <pre className="json-output backup-summary">
            {JSON.stringify(
              {
                filename: lastExport.filename,
                counts,
                warnings: lastExport.manifest.warnings,
              },
              null,
              2,
            )}
          </pre>
        )}
      </Panel>

      <Panel>
        <h2 className="panel-section-title">Import</h2>
        <p className="panel-hint">
          Additive import: titles are queued via items/add; pins call the same
          activate path as the UI. Blacklisted and scrape-only streams are not
          restored. Large libraries may take several minutes.
        </p>
        <div className="form-row form-row--checkboxes">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={skipExisting}
              onChange={(e) => setSkipExisting(e.target.checked)}
            />
            Skip titles already in library
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={restorePins}
              onChange={(e) => setRestorePins(e.target.checked)}
            />
            Restore pinned streams
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={restoreSettings}
              onChange={(e) => setRestoreSettings(e.target.checked)}
            />
            Restore settings.json (overwrites current settings)
          </label>
        </div>
        <div className="form-row">
          <input
            type="file"
            accept=".zip,.riven-backup.zip,application/zip"
            onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="form-actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={importing || !importFile}
            onClick={handleImport}
          >
            {importing ? 'Importing…' : 'Import backup'}
          </button>
        </div>
        {lastImport && (
          <pre className="json-output backup-summary">
            {JSON.stringify(lastImport, null, 2)}
          </pre>
        )}
      </Panel>
    </ViewLayout>
  );
}
