/**
 * Media metadata panel: filename, quality/resolution chips, raw JSON toggle.
 */

import { useState } from 'react';

const MEDIA_METADATA_IS_TAGS: [key: string, string][] = [
  ['is_remastered', 'Remastered'],
  ['is_proper', 'Proper'],
  ['is_repack', 'Repack'],
  ['is_remux', 'Remux'],
  ['is_upscaled', 'Upscaled'],
  ['is_directors_cut', "Director's Cut"],
  ['is_extended', 'Extended'],
];

export interface MediaMetadataProps {
  metadata: Record<string, unknown> | null;
}

function Chip({
  text,
  className = '',
}: {
  text: string;
  className?: string;
}) {
  return <span className={`legend-chip ${className}`.trim()}>{text}</span>;
}

export function MediaMetadata({ metadata }: MediaMetadataProps) {
  const [showRaw, setShowRaw] = useState(false);

  if (!metadata) {
    return (
      <div className="panel item-media-metadata">
        <p className="muted">No media metadata available.</p>
      </div>
    );
  }

  const filename =
    typeof metadata.filename === 'string' ? metadata.filename : '';
  const video = metadata.video as Record<string, unknown> | undefined;
  const qualitySource = metadata.quality_source as string | undefined;
  const w = video?.resolution_width as number | undefined;
  const h = video?.resolution_height as number | undefined;
  const resolutionLabel = video?.resolution_label as string | undefined;
  const resolutionChip = w && h ? `${w}×${h}` : resolutionLabel || '';

  return (
    <div className="panel item-media-metadata">
      <div className="section-head">
        <h3>Media Metadata</h3>
        <button
          type="button"
          className="btn btn--small btn--secondary"
          onClick={() => setShowRaw((v) => !v)}
        >
          {showRaw ? 'Hide raw JSON' : 'Show raw JSON'}
        </button>
      </div>
      <div className="media-metadata-main">
        <div
          className="media-metadata-filename"
          title={filename || ''}
        >
          {filename || '—'}
        </div>
        <div className="media-metadata-chips">
          {MEDIA_METADATA_IS_TAGS.map(([key, label]) =>
            metadata[key] === true ? (
              <Chip key={key} text={label} className="legend-chip--tag" />
            ) : null,
          )}
          {qualitySource && (
            <Chip text={qualitySource} className="legend-chip--quality" />
          )}
          {resolutionChip && (
            <Chip text={resolutionChip} className="legend-chip--resolution" />
          )}
        </div>
      </div>
      {showRaw && (
        <pre className="json-output">
          {JSON.stringify(metadata, null, 2)}
        </pre>
      )}
    </div>
  );
}
