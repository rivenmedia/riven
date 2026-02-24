import { useCallback, useEffect, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../components/ui/PagePrimitives';
import { apiGet } from '../services/api';
import type { AppRoute } from '../app/routeTypes';

interface CalendarEntry {
  aired_at?: string;
  show_title?: string;
  item_type?: string;
}

function toDateKey(iso: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getMonthGrid(
  year: number,
  month: number,
): { date: string | null; dayNum: number | null }[][] {
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

export default function CalendarView({ route }: { route: AppRoute }) {
  const now = new Date();
  const yearFromQuery = parseInt(route.query?.year ?? String(now.getFullYear()), 10);
  const monthFromQuery = parseInt(route.query?.month ?? String(now.getMonth() + 1), 10);
  const [year, setYear] = useState(Math.min(9999, Math.max(1, yearFromQuery)));
  const [month, setMonth] = useState(Math.min(12, Math.max(1, monthFromQuery)));
  const [byDate, setByDate] = useState<Record<string, (CalendarEntry & { aired_at: string })[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setYear(Math.min(9999, Math.max(1, yearFromQuery)));
    setMonth(Math.min(12, Math.max(1, monthFromQuery)));
  }, [yearFromQuery, monthFromQuery]);

  const fetchCalendar = useCallback(async () => {
    setLoading(true);
    const response = await apiGet('/calendar');
    if (!response.ok) {
      setError(response.error || 'Failed to load calendar.');
      setLoading(false);
      return;
    }
    const values = Object.values(
      (response.data as { data?: Record<string, CalendarEntry> })?.data ?? {},
    ) as CalendarEntry[];
    const withDate = values.filter(
      (e): e is CalendarEntry & { aired_at: string } => Boolean(e?.aired_at),
    );
    const map: Record<string, (CalendarEntry & { aired_at: string })[]> = {};
    withDate.forEach((entry) => {
      const key = toDateKey(entry.aired_at);
      if (!map[key]) map[key] = [];
      map[key].push(entry);
    });
    setByDate(map);
    setError(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchCalendar();
  }, [fetchCalendar]);

  const grid = getMonthGrid(year, month);
  const prevMonth = month === 1 ? 12 : month - 1;
  const prevYear = month === 1 ? year - 1 : year;
  const nextMonth = month === 12 ? 1 : month + 1;
  const nextYear = month === 12 ? year + 1 : year;
  const basePath = '#/calendar';

  return (
    <ViewLayout className="view-calendar" view="calendar">
      <ViewHeader
        title="Release Calendar"
        subtitle="Upcoming or recently aired entries from your managed media graph."
      />
      <Panel>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : error ? (
          <p className="muted">{error}</p>
        ) : (
          <>
            <div className="calendar-nav">
              <a
                className="btn btn--secondary btn--small"
                href={`${basePath}?year=${prevYear}&month=${prevMonth}`}
              >
                ← Prev
              </a>
              <h2 className="calendar-title">
                {MONTHS[month - 1]} {year}
              </h2>
              <a
                className="btn btn--secondary btn--small"
                href={`${basePath}?year=${nextYear}&month=${nextMonth}`}
              >
                Next →
              </a>
            </div>
            <div className="calendar-grid">
              <div className="calendar-week calendar-week--head">
                {WEEKDAYS.map((w) => (
                  <div key={w} className="calendar-weekday">
                    {w}
                  </div>
                ))}
              </div>
              {grid.map((week, wi) => (
                <div key={wi} className="calendar-week">
                  {week.map((cell, ci) => {
                    if (cell.dayNum === null) {
                      return (
                        <div
                          key={ci}
                          className="calendar-day calendar-day--empty"
                        />
                      );
                    }
                    const entries = (byDate[cell.date!] || []).slice(0, 5);
                    const more = (byDate[cell.date!]?.length || 0) - entries.length;
                    const today =
                      year === now.getFullYear() &&
                      month === now.getMonth() + 1 &&
                      cell.dayNum === now.getDate();
                    return (
                      <div
                        key={ci}
                        className={`calendar-day ${today ? 'calendar-day--today' : ''}`}
                        data-date={cell.date!}
                      >
                        <div className="calendar-day-num">{cell.dayNum}</div>
                        <div className="calendar-day-entries">
                          {entries.map((e, i) => (
                            <div
                              key={i}
                              className="calendar-entry"
                              title={e.show_title || 'Unknown'}
                            >
                              <span
                                className={
                                  e.item_type === 'movie'
                                    ? 'legend-chip legend-chip--movie'
                                    : 'legend-chip legend-chip--tv'
                                }
                              >
                                {e.item_type || ''}
                              </span>{' '}
                              {e.show_title || 'Unknown'}
                            </div>
                          ))}
                          {more > 0 && (
                            <div className="calendar-day-more">+{more} more</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>
    </ViewLayout>
  );
}
