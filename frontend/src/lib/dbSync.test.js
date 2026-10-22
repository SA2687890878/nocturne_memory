import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('./api', () => ({
  getDatabaseStatus: vi.fn(),
}));

import { getDatabaseStatus } from './api';
import { watchDatabaseChanges } from './dbSync';

const flush = () => new Promise(r => setTimeout(r, 0));

describe('watchDatabaseChanges', () => {
  beforeEach(() => {
    vi.mocked(getDatabaseStatus).mockReset();
  });

  it('reloads when the server DB changed after the page loaded', async () => {
    const reload = vi.fn();
    vi.mocked(getDatabaseStatus).mockResolvedValue({ effective_url: 'db-a' });
    const stop = watchDatabaseChanges(reload);
    await flush();
    expect(reload).not.toHaveBeenCalled();

    vi.mocked(getDatabaseStatus).mockResolvedValue({ effective_url: 'db-b' });
    window.dispatchEvent(new Event('focus'));
    await flush();

    expect(reload).toHaveBeenCalledTimes(1);
    stop();
  });

  it('does not reload while the DB is unchanged', async () => {
    const reload = vi.fn();
    vi.mocked(getDatabaseStatus).mockResolvedValue({ effective_url: 'db-a' });
    const stop = watchDatabaseChanges(reload);
    await flush();

    window.dispatchEvent(new Event('focus'));
    await flush();

    expect(reload).not.toHaveBeenCalled();
    stop();
  });

  it('ignores errors instead of reloading', async () => {
    const reload = vi.fn();
    vi.mocked(getDatabaseStatus).mockRejectedValue(new Error('offline'));
    const stop = watchDatabaseChanges(reload);
    await flush();

    window.dispatchEvent(new Event('focus'));
    await flush();

    expect(reload).not.toHaveBeenCalled();
    stop();
  });
});
