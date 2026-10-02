export function formatDuration(totalSeconds: number): string {
  const rounded = Math.round(totalSeconds);
  const minutes = Math.floor(rounded / 60);
  const seconds = String(rounded % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

/** A signed m:ss, e.g. "+0:20" or "-1:05". Zero is unsigned. */
export function formatSignedDuration(totalSeconds: number): string {
  if (Math.round(totalSeconds) === 0) return formatDuration(0);
  const sign = totalSeconds > 0 ? "+" : "-";
  return `${sign}${formatDuration(Math.abs(totalSeconds))}`;
}
