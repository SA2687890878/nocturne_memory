import React from 'react';
import clsx from 'clsx';
import { useLocale } from '../../../i18n/useLocale';
import { lifecycleLabel, normalizeLifecycleStatus } from '../../../lib/lifecycle';

const STATUS_STYLES = {
  active: 'bg-emerald-950/30 text-emerald-400 border-emerald-800/30',
  completed: 'bg-sky-950/30 text-sky-400 border-sky-800/30',
  obsolete: 'bg-amber-950/30 text-amber-400 border-amber-800/30',
  unspecified: 'bg-slate-800/30 text-slate-500 border-slate-700/30',
};

const LifecycleBadge = ({ status, size = 'sm' }) => {
  const { t } = useLocale();
  if (!status) return null;

  const normalized = normalizeLifecycleStatus(status);
  const sizeClass = size === 'lg'
    ? 'px-2.5 py-1 text-xs'
    : 'px-1.5 py-0.5 text-[10px]';

  return (
    <span
      data-lifecycle-status={normalized}
      title={t('memory.lifecycle.label')}
      className={clsx('inline-flex items-center rounded border font-medium', STATUS_STYLES[normalized], sizeClass)}
    >
      {lifecycleLabel(t, normalized)}
    </span>
  );
};

export default LifecycleBadge;
