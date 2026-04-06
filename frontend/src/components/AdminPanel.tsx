import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { GameState } from '../types/gameState';

interface Props {
  backend: string;
  onStateLoaded: (state: GameState) => void;
}

export default function AdminPanel({ backend, onStateLoaded }: Props) {
  const { t } = useTranslation();
  const [files, setFiles] = useState<string[]>([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${backend}/api/admin/test-states`)
      .then(r => r.json())
      .then((list: string[]) => {
        setFiles(list);
        if (list.length > 0) setSelected(list[0]);
      })
      .catch(e => setError(e.message));
  }, [backend]);

  async function loadState() {
    if (!selected) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`${backend}/api/admin/load-test-state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: selected }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      const gs: GameState = await res.json();
      onStateLoaded(gs);
      setSuccess(t('admin.loaded', { name: selected }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="admin-panel">
      <h3>{t('admin.title')}</h3>
      <div className="admin-section">
        <label className="admin-label">{t('admin.label')}</label>
        <select
          className="admin-select"
          value={selected}
          onChange={e => { setSelected(e.target.value); setSuccess(null); }}
        >
          {files.map(f => (
            <option key={f} value={f}>{f.replace('.json', '')}</option>
          ))}
        </select>
        <button
          className="admin-btn"
          onClick={loadState}
          disabled={loading || !selected}
        >
          {loading ? t('admin.loading') : t('admin.load')}
        </button>
        {error && <span className="admin-error">{error}</span>}
        {success && <span className="admin-success">{success}</span>}
      </div>
    </div>
  );
}
