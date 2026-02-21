import { apiGet } from '../services/api';
import type { AppRoute } from '../app/routeTypes';

interface CalendarEntry {
  aired_at?: string;
  show_title?: string;
  item_type?: string;
  last_state?: string;
}

function toDateKey(iso: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getMonthGrid(year: number, month: number): { date: string | null; dayNum: number | null }[][] {
  const first = new Date(year, month - 1, 1);
  const last = new Date(year, month, 0);
  const startWeekday = first.getDay();
  const daysInMonth = last.getDate();

  const weeks: { date: string | null; dayNum: number | null }[][] = [];
  let week: { date: string | null; dayNum: number | null }[] = [];

  const pad = (n: number) => String(n).padStart(2, '0');
  const dateStr = (d: number) => `${year}-${pad(month)}-${pad(d)}`;

  for (let i = 0; i < startWeekday; i++) {
    week.push({ date: null, dayNum: null });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    week.push({ date: dateStr(d), dayNum: d });
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  }
  if (week.length) {
    while (week.length < 7) week.push({ date: null, dayNum: null });
    weeks.push(week);
  }
  return weeks;
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function escapeHtml(s: string): string {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

export async function load(route: AppRoute, container: HTMLElement) {
  const content = container.querySelector('[data-slot="content"]');
  if (!content) return;

  const now = new Date();
  const year = Math.min(9999, Math.max(1, parseInt(route.query?.year || String(now.getFullYear()), 10)));
  const month = Math.min(12, Math.max(1, parseInt(route.query?.month || String(now.getMonth() + 1), 10)));

  const response = await apiGet('/calendar');
  if (!response.ok) {
    content.innerHTML = `<p class="muted">${escapeHtml(response.error || 'Failed to load calendar.')}</p>`;
    return;
  }

  const values = Object.values(
    (response.data as { data?: Record<string, CalendarEntry> })?.data || {},
  ) as CalendarEntry[];
  const withDate = values.filter(
    (e): e is CalendarEntry & { aired_at: string } => Boolean(e?.aired_at),
  );

  const byDate: Record<string, (CalendarEntry & { aired_at: string })[]> = {};
  withDate.forEach((entry) => {
    const key = toDateKey(entry.aired_at);
    if (!byDate[key]) byDate[key] = [];
    byDate[key].push(entry);
  });

  const grid = getMonthGrid(year, month);
  const prevMonth = month === 1 ? 12 : month - 1;
  const prevYear = month === 1 ? year - 1 : year;
  const nextMonth = month === 12 ? 1 : month + 1;
  const nextYear = month === 12 ? year + 1 : year;
  const basePath = '#/calendar';

  const dayCells = grid
    .map(
      (week) =>
        `<div class="calendar-week">${week
          .map((cell) => {
            if (cell.dayNum === null) {
              return `<div class="calendar-day calendar-day--empty"></div>`;
            }
            const entries = (byDate[cell.date!] || []).slice(0, 5);
            const more = (byDate[cell.date!]?.length || 0) - entries.length;
            const today =
              year === now.getFullYear() &&
              month === now.getMonth() + 1 &&
              cell.dayNum === now.getDate();
            const entriesHtml = entries
              .map((e) => {
                const chip = e.item_type === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv';
                const title = escapeHtml(e.show_title || 'Unknown');
                return `<div class="calendar-entry" title="${title}"><span class="legend-chip ${chip}">${escapeHtml(e.item_type || '')}</span> ${title}</div>`;
              })
              .join('');
            const moreHtml =
              more > 0 ? `<div class="calendar-day-more">+${more} more</div>` : '';
            return `
              <div class="calendar-day ${today ? 'calendar-day--today' : ''}" data-date="${escapeHtml(cell.date!)}">
                <div class="calendar-day-num">${cell.dayNum}</div>
                <div class="calendar-day-entries">${entriesHtml}${moreHtml}</div>
              </div>`;
          })
          .join('')}</div>`,
    )
    .join('');

  content.innerHTML = `
    <div class="calendar-nav">
      <a class="btn btn--secondary btn--small" href="${basePath}?year=${prevYear}&month=${prevMonth}">← Prev</a>
      <h2 class="calendar-title">${escapeHtml(MONTHS[month - 1])} ${year}</h2>
      <a class="btn btn--secondary btn--small" href="${basePath}?year=${nextYear}&month=${nextMonth}">Next →</a>
    </div>
    <div class="calendar-grid">
      <div class="calendar-week calendar-week--head">
        ${WEEKDAYS.map((w) => `<div class="calendar-weekday">${w}</div>`).join('')}
      </div>
      ${dayCells}
    </div>
  `;
}
