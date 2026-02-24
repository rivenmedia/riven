import { MediaTypeToggle, type MediaTypeValue } from '../../ui/MediaTypeToggle';

export type ExploreToolbarProps = {
  source: 'tmdb' | 'tvdb';
  mode: 'search' | 'discover';
  mediaType: MediaTypeValue;
  timeWindow: 'day' | 'week';
  trendingMode: boolean;
  searchQuery: string;
  onSourceChange: (v: 'tmdb' | 'tvdb') => void;
  onModeChange: (v: 'search' | 'discover') => void;
  onMediaTypeChange: (v: MediaTypeValue) => void;
  onTimeWindowChange: (v: 'day' | 'week') => void;
  onSearchQueryChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  showTrendingWindow: boolean;
};

export function ExploreToolbar({
  source,
  mode,
  mediaType,
  timeWindow,
  searchQuery,
  onSourceChange,
  onModeChange,
  onMediaTypeChange,
  onTimeWindowChange,
  onSearchQueryChange,
  onSubmit,
  showTrendingWindow,
}: ExploreToolbarProps) {
  return (
    <form className="toolbar toolbar--explore" onSubmit={onSubmit}>
      <select value={source} onChange={(e) => onSourceChange(e.target.value as 'tmdb' | 'tvdb')}>
        <option value="tmdb">TMDB</option>
        <option value="tvdb">TVDB</option>
      </select>
      <select value={mode} onChange={(e) => onModeChange(e.target.value as 'search' | 'discover')}>
        <option value="search">Search</option>
        <option value="discover">Discover</option>
      </select>
      <MediaTypeToggle value={mediaType} includeAll onChange={onMediaTypeChange} />
      {showTrendingWindow && (
        <select value={timeWindow} onChange={(e) => onTimeWindowChange(e.target.value as 'day' | 'week')}>
          <option value="day">Today</option>
          <option value="week">This Week</option>
        </select>
      )}
      <input
        type="search"
        placeholder="Search title / person / keywords"
        value={searchQuery}
        onChange={(e) => onSearchQueryChange(e.target.value)}
      />
      <button className="btn btn--primary" type="submit">
        Load
      </button>
    </form>
  );
}
