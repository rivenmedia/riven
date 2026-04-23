import { apiPost } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import { getMediaKind } from '../../shared/utils/utils';

export async function addDiscoverItemToLibrary(
  item: any,
  seasonNumbers: number[] | null = null,
): Promise<boolean> {
  const kind = getMediaKind(item);
  if (kind !== 'movie' && kind !== 'tv') return false;

  let payload: any;
  if (kind === 'movie') {
    payload = { tmdb_ids: [String(item.tmdb_id || item.id)], media_type: 'movie' };
  } else if (item.indexer === 'tvdb') {
    payload = { tvdb_ids: [String(item.tvdb_id || item.id)], media_type: 'tv' };
  } else {
    payload = { tmdb_ids: [String(item.tmdb_id || item.id)], media_type: 'tv' };
  }

  const res = await apiPost('/items/add', payload);
  if (!res.ok) {
    notify(res.error || 'Failed to add media', 'error');
    return false;
  }

  if (kind === 'tv' && seasonNumbers && seasonNumbers.length > 0) {
    const scrapePayload: any = { media_type: 'tv', season_numbers: seasonNumbers };
    if (item.indexer === 'tvdb') {
      scrapePayload.tvdb_id = String(item.tvdb_id || item.id);
    } else {
      scrapePayload.tmdb_id = String(item.tmdb_id || item.id);
    }
    const scrapeRes = await apiPost('/scrape/auto', scrapePayload);
    if (!scrapeRes.ok) {
      notify(`Added to library but failed to start season scrape: ${scrapeRes.error}`, 'warning');
      return true;
    }
    notify(`Added "${item.title || item.name}" — scraping ${seasonNumbers.length} season(s)`, 'success');
    return true;
  }

  notify(`Added "${item.title || item.name}" to library`, 'success');
  return true;
}
