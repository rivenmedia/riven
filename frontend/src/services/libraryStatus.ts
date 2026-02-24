import { apiGet } from './api';
import { getMediaKind } from './utils';
import { toCsv } from './utils';

/**
 * Annotates items with in_library, library_item_id, library_state from GET /items/library/status.
 * Mutates items in place. Only processes movie/tv items.
 */
export async function annotateLibraryStatus(items: any[]): Promise<any[]> {
  const media = items.filter((item) => {
    const kind = getMediaKind(item);
    return kind === 'movie' || kind === 'tv';
  });

  if (!media.length) return items;

  const tmdbIds: string[] = [];
  const tvdbIds: string[] = [];
  media.forEach((item) => {
    if (item.indexer === 'tvdb') {
      tvdbIds.push(String(item.tvdb_id || item.id));
      return;
    }
    tmdbIds.push(String(item.tmdb_id || item.id));
    if (item.tvdb_id) tvdbIds.push(String(item.tvdb_id));
  });

  const res = await apiGet('/items/library/status', {
    tmdb_ids: toCsv(tmdbIds),
    tvdb_ids: toCsv(tvdbIds),
  });
  if (!res.ok) return items;

  media.forEach((item) => {
    const tmdbKey = String(item.tmdb_id || item.id);
    const tvdbKey = String(item.tvdb_id || item.id);
    const status =
      (item.indexer === 'tvdb' ? res.data?.tvdb?.[tvdbKey] : null) ||
      res.data?.tmdb?.[tmdbKey] ||
      res.data?.tvdb?.[tvdbKey];
    if (!status) return;
    item.in_library = Boolean(status.in_library);
    item.library_item_id = status.library_item_id ?? null;
    item.library_state = status.library_state ?? null;
  });

  return items;
}
