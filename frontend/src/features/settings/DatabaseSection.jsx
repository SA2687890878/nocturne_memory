import React, { useState, useEffect } from 'react';
import {
  Plus, CheckCircle, XCircle, RefreshCw, TestTube, FolderOpen
} from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { testDatabase, createDatabase, openDbFolder, switchDatabase, pickDatabasePath } from '../../lib/api';
import { toast } from '../../components/Toast';

function parseSqlitePathFromUrl(url) {
  if (!url || !url.includes('sqlite')) return '';
  const m = url.match(/\/\/\/(.+)$/);
  return m ? m[1] : '';
}

// Recents live in this browser: switching DB is a process-wide page action that
// config.json deliberately does not persist, so there is nothing server-side.
const RECENT_DBS_KEY = 'nocturne:recent_dbs';
const MAX_RECENT_DBS = 5;

function loadRecentDbs() {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_DBS_KEY));
    return Array.isArray(list) ? list.filter((u) => typeof u === 'string') : [];
  } catch {
    return [];
  }
}

function saveRecentDbs(list) {
  try {
    localStorage.setItem(RECENT_DBS_KEY, JSON.stringify(list));
  } catch {
    // private mode / quota: recents are a convenience, never fail the switch over them
  }
  return list;
}

function rememberDb(url) {
  return saveRecentDbs([url, ...loadRecentDbs().filter((u) => u !== url)].slice(0, MAX_RECENT_DBS));
}

const dbFileName = (url) => parseSqlitePathFromUrl(url).split('/').filter(Boolean).pop() || url;

export default function DatabaseSection({ settings, dbStatus, onRefreshStatus }) {
  const { t } = useTranslation();
  // effective_url is what the server process is actually serving (browsing override).
  const currentUrl = dbStatus?.effective_url || settings?.database_url || '';
  const isSqliteCurrent = currentUrl.includes('sqlite');

  const [mode, setMode] = useState(isSqliteCurrent ? 'sqlite' : 'postgresql');
  const [sqlitePath, setSqlitePath] = useState('');
  const [pgUrl, setPgUrl] = useState('');
  const [newDbPath, setNewDbPath] = useState('');
  const [creating, setCreating] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [recentDbs, setRecentDbs] = useState(loadRecentDbs);
  const [openingDb, setOpeningDb] = useState(null);
  const [picking, setPicking] = useState(false);

  useEffect(() => {
    if (!currentUrl) return;
    if (currentUrl.includes('sqlite')) {
      setMode('sqlite');
      setSqlitePath(parseSqlitePathFromUrl(currentUrl));
      // The DB this page booted on was opened too, so it must be one click away.
      setRecentDbs(rememberDb(currentUrl));
    } else {
      setMode('postgresql');
      setPgUrl(currentUrl);
    }
  }, [currentUrl]);

  const buildUrl = () => {
    if (mode === 'sqlite') {
      const p = sqlitePath.trim().replace(/\\/g, '/');
      return p ? `sqlite+aiosqlite:///${p}` : '';
    }
    return pgUrl.trim();
  };

  const inputValue = mode === 'sqlite' ? sqlitePath : pgUrl;
  const hasInput = inputValue.trim().length > 0;

  const handleTestOnly = async () => {
    const url = buildUrl();
    if (!url) return;
    setBusy(true);
    setTestResult(null);
    try {
      const result = await testDatabase(url);
      setTestResult(result);
    } catch (e) {
      setTestResult({ success: false, message: e.response?.data?.detail || e.message });
    } finally {
      setBusy(false);
    }
  };

  const handleTestAndSave = async () => {
    const url = buildUrl();
    if (!url) return;
    setBusy(true);
    setTestResult(null);
    try {
      const result = await testDatabase(url);
      if (result.success) {
        await switchDatabase(url);   // browsing only, config.json untouched
        setRecentDbs(rememberDb(url));
        setTestResult({ success: true, message: t('settings.database.switched') });
        window.location.reload();    // reload so the whole app reads the new DB
      } else {
        setTestResult(result);
      }
    } catch (e) {
      setTestResult({ success: false, message: e.response?.data?.detail || e.message });
    } finally {
      setBusy(false);
    }
  };

  const handleCreate = async () => {
    const path = newDbPath.trim();
    if (!path) return;
    setCreating(true);
    setTestResult(null);
    try {
      const result = await createDatabase(path);
      setMode('sqlite');
      setSqlitePath(parseSqlitePathFromUrl(result.database_url));
      setDirty(true);
      setNewDbPath('');
      setTestResult({ success: true, message: t('settings.database.created_switch') });
    } catch (e) {
      setTestResult({ success: false, message: e.response?.data?.detail || e.message });
    } finally {
      setCreating(false);
    }
  };

  const handleBrowse = async (target) => {
    setPicking(true);
    try {
      const result = await pickDatabasePath(target === 'new' ? 'save' : 'open');
      if (!result.success) return;   // user cancelled the dialog
      if (target === 'new') {
        setNewDbPath(result.path);
      } else {
        setSqlitePath(result.path);
        setDirty(true);
        setTestResult(null);
      }
    } catch (e) {
      setTestResult({ success: false, message: e.response?.data?.detail || e.message });
    } finally {
      setPicking(false);
    }
  };

  const handleOpenRecent = async (url) => {
    setOpeningDb(url);
    try {
      await switchDatabase(url);
      rememberDb(url);
      window.location.reload();
    } catch (e) {
      setTestResult({ success: false, message: e.response?.data?.detail || e.message });
      // 404: the file moved or was deleted, so stop offering a dead entry.
      if (e.response?.status === 404) {
        setRecentDbs(saveRecentDbs(loadRecentDbs().filter((u) => u !== url)));
      }
    } finally {
      setOpeningDb(null);
    }
  };

  const handleOpenFolder = async () => {
    try {
      await openDbFolder();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, "error");
    }
  };

  return (
    <div className="space-y-5 pt-4">
      {/* Status card */}
      {dbStatus && (
        <div className="bg-slate-900 border border-slate-700/50 shadow-sm rounded-lg p-3 text-sm space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-slate-400">{t('settings.database.type_label')}</span>
            <span className="text-slate-200 font-medium">{dbStatus.type === 'sqlite' ? t('settings.database.sqlite') : t('settings.database.postgresql')}</span>
          </div>
          {dbStatus.type === 'sqlite' && dbStatus.path && (
            <>
              <div className="flex items-center justify-between gap-4">
                <span className="text-slate-400 flex-shrink-0">{t('settings.database.path_label')}</span>
                <span className="text-slate-300 font-mono text-xs truncate max-w-[380px]" title={dbStatus.path}>{dbStatus.path}</span>
              </div>
              {dbStatus.size_display && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">{t('settings.database.size_label')}</span>
                  <span className="text-slate-200">{dbStatus.size_display}</span>
                </div>
              )}
            </>
          )}
          {dbStatus.type === 'postgresql' && dbStatus.url_masked && (
            <div className="flex items-center justify-between">
              <span className="text-slate-400">{t('settings.database.url_label')}</span>
              <span className="text-slate-300 font-mono text-xs">{dbStatus.url_masked}</span>
            </div>
          )}
          {dbStatus.effective_url && dbStatus.database_url &&
            dbStatus.effective_url !== dbStatus.database_url && (
            <div className="text-xs text-amber-400/90">{t('settings.database.browsing_note')}</div>
          )}
          <div className="flex items-center justify-end gap-3 pt-1">
            {dbStatus.type === 'sqlite' && dbStatus.path && (
              <button onClick={handleOpenFolder} className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1 transition-colors">
                <FolderOpen size={11} /> {t('settings.database.open_folder')}
              </button>
            )}
            <button onClick={onRefreshStatus} className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
              <RefreshCw size={11} /> {t('settings.database.refresh')}
            </button>
          </div>
        </div>
      )}

      {/* Mode toggle */}
      <div className="space-y-2">
        <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider">{t('settings.database.type_selector_label')}</label>
        <div className="flex rounded-lg overflow-hidden border border-slate-700 w-fit">
          {[
            { id: 'sqlite', label: t('settings.database.sqlite') },
            { id: 'postgresql', label: t('settings.database.postgresql') },
          ].map(opt => (
            <button
              key={opt.id}
              onClick={() => { setMode(opt.id); setDirty(true); setTestResult(null); }}
              className={clsx(
                "px-4 py-1.5 text-sm font-medium transition-colors",
                mode === opt.id
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Connection input */}
      <div className="space-y-2">
        <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider">
          {mode === 'sqlite' ? t('settings.database.file_path_label') : t('settings.database.connection_url_label')}
        </label>
        {mode === 'sqlite' ? (
          <div className="flex gap-2">
            <input
              type="text"
              value={sqlitePath}
              onChange={e => { setSqlitePath(e.target.value); setDirty(true); setTestResult(null); }}
              placeholder={t('settings.database.sqlite_placeholder')}
              className="flex-1 bg-slate-950 border border-slate-700 text-slate-200 rounded-lg px-3 py-2 text-sm font-mono placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-inner"
            />
            <button
              type="button"
              onClick={() => handleBrowse('path')}
              disabled={picking}
              aria-label={t('settings.database.browse')}
              className="px-3 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-slate-200 rounded-lg text-sm flex items-center gap-1.5 transition-colors whitespace-nowrap"
            >
              <FolderOpen size={14} /> {t('settings.database.browse')}
            </button>
          </div>
        ) : (
          <input
            type="text"
            value={pgUrl}
            onChange={e => { setPgUrl(e.target.value); setDirty(true); setTestResult(null); }}
            placeholder={t('settings.database.pg_placeholder')}
            className="w-full bg-slate-950 border border-slate-700 text-slate-200 rounded-lg px-3 py-2 text-sm font-mono placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-inner"
          />
        )}

        {mode === 'sqlite' && recentDbs.some(u => u !== currentUrl) && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">{t('settings.database.recent_label')}</span>
            {recentDbs.filter(u => u !== currentUrl).map(url => (
              <button
                key={url}
                type="button"
                onClick={() => handleOpenRecent(url)}
                disabled={!!openingDb}
                title={parseSqlitePathFromUrl(url)}
                className="max-w-[220px] truncate px-2 py-1 text-xs font-mono rounded-md bg-slate-900 border border-slate-700 text-slate-300 hover:border-indigo-500 hover:text-slate-100 disabled:opacity-40 transition-colors"
              >
                {openingDb === url ? t('settings.database.opening') : dbFileName(url)}
              </button>
            ))}
          </div>
        )}

        {hasInput && (
          <button
            onClick={dirty ? handleTestAndSave : handleTestOnly}
            disabled={busy}
            className="mt-1 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-lg text-sm flex items-center gap-1.5 transition-colors"
          >
            <TestTube size={14} />
            {busy ? t('settings.database.testing') : (dirty ? t('settings.database.test_save') : t('settings.database.test_connection'))}
          </button>
        )}

        {testResult && (
          <div className={`flex items-center gap-2 text-sm ${testResult.success ? 'text-emerald-400' : 'text-red-400'}`}>
            {testResult.success ? <CheckCircle size={14} /> : <XCircle size={14} />}
            {testResult.message}
          </div>
        )}
      </div>

      {/* Create new SQLite DB */}
      {mode === 'sqlite' && (
        <div className="space-y-2 pt-2 border-t border-slate-800/50">
          <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider">{t('settings.database.create_new_label')}</label>
          <p className="text-xs text-slate-500">{t('settings.database.create_new_desc')}</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={newDbPath}
              onChange={e => setNewDbPath(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder={t('settings.database.new_db_placeholder')}
              className="flex-1 bg-slate-950 border border-slate-700 text-slate-200 rounded-lg px-3 py-2 text-sm font-mono placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-inner"
            />
            <button
              type="button"
              onClick={() => handleBrowse('new')}
              disabled={picking}
              aria-label={t('settings.database.browse')}
              title={t('settings.database.browse')}
              className="px-3 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-slate-200 rounded-lg flex items-center transition-colors"
            >
              <FolderOpen size={14} />
            </button>
            <button
              onClick={handleCreate}
              disabled={creating || !newDbPath.trim()}
              className="px-3 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-slate-200 rounded-lg text-sm flex items-center gap-1.5 transition-colors whitespace-nowrap"
            >
              <Plus size={14} />
              {creating ? t('settings.database.creating') : t('settings.database.create')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
