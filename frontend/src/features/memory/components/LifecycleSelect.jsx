import React from 'react';
import { useLocale } from '../../../i18n/useLocale';
import { LIFECYCLE_STATUSES, normalizeLifecycleStatus } from '../../../lib/lifecycle';

const LifecycleSelect = ({ id, value, onChange, disabled = false }) => {
  const { t } = useLocale();

  return (
    <select
      id={id}
      value={normalizeLifecycleStatus(value)}
      onChange={e => onChange(e.target.value)}
      disabled={disabled}
      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500/50 transition-colors disabled:opacity-50"
    >
      {LIFECYCLE_STATUSES.map(status => (
        <option key={status} value={status}>{t(`memory.lifecycle.${status}`)}</option>
      ))}
    </select>
  );
};

export default LifecycleSelect;
