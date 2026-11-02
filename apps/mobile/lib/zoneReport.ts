/**
 * The phone's zone report to the server while it is in flight (`hooks/useBootstrapSync.ts`
 * sends it). Every to-do's `notify_at` is worked out in the server's copy of the zone, so
 * the to-do read a return to the foreground sends waits for the report that same return
 * started: the read the report asks for once it lands (`userUpdated`) is then the only one,
 * and nothing is read in the old zone first.
 */
let inFlight: Promise<unknown> | null = null;

/** `report` is the zone report in flight until it settles. */
export function trackZoneReport(report: Promise<unknown>): void {
  inFlight = report;
  const settled = () => {
    if (inFlight === report) inFlight = null;
  };
  void report.then(settled, settled);
}

/**
 * Resolves once the zone report in flight, if any, has settled. A return to the foreground
 * reaches every listener in one pass, and a listener may run before the one that starts the
 * report: the first wait lets that pass finish.
 */
export async function zoneReportSettled(): Promise<void> {
  await Promise.resolve();
  const report = inFlight;
  if (report) await report.then(() => undefined, () => undefined);
}
