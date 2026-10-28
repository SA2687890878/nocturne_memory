export const LIFECYCLE_STATUSES = ['active', 'completed', 'obsolete', 'unspecified'];

export const DEFAULT_LIFECYCLE_STATUS = 'unspecified';

export const isLifecycleStatus = (value) => LIFECYCLE_STATUSES.includes(value);

export const normalizeLifecycleStatus = (value) =>
  isLifecycleStatus(value) ? value : DEFAULT_LIFECYCLE_STATUS;

export const lifecycleLabel = (t, value) =>
  t(`memory.lifecycle.${normalizeLifecycleStatus(value)}`);
