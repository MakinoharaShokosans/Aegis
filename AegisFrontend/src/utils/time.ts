/**
 * Time formatting utilities
 */

/**
 * Format timestamp into relative time string matching the reference UI:
 * e.g. "刚刚", "14m", "2h", "1d", "3d", "8d", "13d", "2mo"
 */
export function formatRelativeTime(dateString?: string | number): string {
  if (!dateString) return '刚刚';
  const date = typeof dateString === 'number' ? new Date(dateString * 1000) : new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  if (isNaN(diffMs) || diffMs < 0) return '刚刚';

  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMinutes < 1) return '刚刚';
  if (diffMinutes < 60) return `${diffMinutes}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 30) return `${diffDays}d`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo`;
  return `${Math.floor(diffDays / 365)}y`;
}
