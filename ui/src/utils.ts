export function formatElapsed(seconds: number): string {
  if (seconds < 0) seconds = 0;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  return `${Math.round(seconds)}s`;
}

export function getTerminalWidth(): number {
  return process.stdout.columns ?? 100;
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 1) + "…";
}

export function weatherEmoji(desc: string): string {
  if (!desc) return "🌡";
  const d = desc.trim().toLowerCase();
  if (d.includes("clear") || d.includes("晴")) return d === "clear" ? "☀️" : "🌤️";
  if (d.includes("fog") || d.includes("霧")) return "🌫️";
  if (d.includes("rain") || d.includes("雨")) return "🌧️";
  if (d.includes("snow") || d.includes("雪")) return "❄️";
  if (d.includes("thunder") || d.includes("雷")) return "⛈️";
  if (d.includes("cloud") || d.includes("曇") || d.includes("partly")) return "☁️";
  return "🌡️";
}
