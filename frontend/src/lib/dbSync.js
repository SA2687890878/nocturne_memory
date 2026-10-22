// Another tab may switch the DB of this server process. Compare on return-to-tab
// and reload, so this page never writes into a DB it isn't showing.
export function watchDatabaseChanges(reload = () => window.location.reload()) {
  let bootUrl = null;
  let disposed = false;

  const sync = async () => {
    try {
      const { getDatabaseStatus } = await import('./api');
      const status = await getDatabaseStatus();
      if (disposed) return;
      if (bootUrl === null) {
        bootUrl = status.effective_url;
      } else if (status.effective_url !== bootUrl) {
        reload();
      }
    } catch {
      // Backend unreachable: leave the page alone.
    }
  };

  const onVisible = () => {
    if (!document.hidden) sync();
  };

  sync();
  window.addEventListener('focus', onVisible);
  document.addEventListener('visibilitychange', onVisible);

  return () => {
    disposed = true;
    window.removeEventListener('focus', onVisible);
    document.removeEventListener('visibilitychange', onVisible);
  };
}
