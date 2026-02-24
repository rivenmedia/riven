/**
 * External reference links (IMDB, TVDB, TMDB). Only links with a value are shown.
 */

export interface ReferenceLinksProps {
  imdb_id?: string | null;
  tvdb_id?: string | null;
  tmdb_id?: string | null;
  type?: 'movie' | 'tv' | string | null;
}

const IMDB_LOGO_URL =
  'https://upload.wikimedia.org/wikipedia/commons/6/69/IMDB_Logo_2016.svg';

function imdbUrl(id: string): string {
  const raw = String(id).trim();
  const tid = raw.startsWith('tt') ? raw : `tt${raw}`;
  return `https://www.imdb.com/title/${tid}/`;
}

function tvdbUrl(id: string): string {
  return `https://thetvdb.com/search?query=${encodeURIComponent(String(id).trim())}`;
}

function tmdbUrl(id: string, type?: string): string {
  const path = type === 'tv' ? 'tv' : 'movie';
  return `https://www.themoviedb.org/${path}/${encodeURIComponent(String(id).trim())}`;
}

const TVDB_SVG = (
  <svg viewBox="0 0 100 54" width={28} height={15} aria-hidden={true} className="reference-links__tvdb-logo">
    <g stroke="none" strokeWidth="1" fill="none" fillRule="evenodd">
      <path
        d="M0,5.09590006 C0,1.81024006 2.9636,-0.441498938 6.46228,0.0733078623 L6.46228,0.0733078623 L52.10124,6.03470006 C54.15254,6.33652006 55.78724,8.54666006 55.78724,10.9536001 L55.78724,10.9536001 L55.78654,17.1835001 C51.94104,19.7605001 49.42044,24.0737001 49.42044,28.9596001 C49.42044,33.8924001 51.87974,38.1680001 55.78724,40.7361001 L55.78724,40.7361001 L55.78724,43.4756001 C55.78724,45.8825001 54.15254,48.0927001 52.10124,48.3945001 L52.10124,48.3945001 L11.60314,53.9266001 C8.10444,54.4417001 5.14084,52.1897001 5.14084,48.9040001 L5.14084,48.9040001 Z M19.68044,10.8218001 L13.66114,10.8218001 L13.66114,18.7064001 L9.84244,18.7064001 L9.84244,23.2621001 L13.66114,23.2621001 L13.66114,32.0227001 C13.4846091,37.5274601 15.6467584,39.9923503 20.6149401,40.0386142 L25.25134,40.0387001 L25.25134,35.4830001 L22.87064,35.4830001 C20.17484,35.3516001 19.59134,34.5631001 19.68074,31.0149001 L19.68074,23.2617001 L27.08014,23.2617001 L33.93424,40.0384001 L40.40294,40.0384001 L49.83694,18.7061001 L43.45734,18.7061001 L37.34794,33.3806001 L31.77694,18.7064001 L19.68044,18.7064001 L19.68044,10.8218001 Z"
        fill="#6CD591"
        fillRule="nonzero"
      />
      <path
        d="M88.60974,18.2771001 C92.51784,18.2771001 95.12314,19.2407001 97.09994,21.4310001 C98.71734,23.1831001 99.57074,25.7677001 99.57074,28.6584001 C99.57074,32.8634001 97.86394,36.1487001 94.76414,38.0323001 C92.74234,39.2590001 90.99054,39.6094001 87.03734,39.6094001 L77.24404,39.6094001 L77.24404,10.3925001 L83.26404,10.3925001 L83.26404,18.2771001 L88.60974,18.2771001 Z M83.26404,35.0537001 L87.71094,35.0537001 C91.26004,35.0537001 93.41634,32.6884001 93.41634,28.8334001 C93.41634,24.8035001 91.52964,22.8324001 87.71094,22.8324001 L83.26404,22.8324001 L83.26404,35.0537001 Z"
        fill="#FFFFFF"
        fillRule="nonzero"
      />
      <path
        d="M68.01354,10.3925001 L74.03354,10.3925001 L74.03354,39.6094001 L63.65594,39.6094001 C59.43354,39.6094001 57.41174,38.9962001 55.25524,37.1126001 C53.05394,35.1416001 51.93124,32.3384001 51.93124,28.7898001 C51.93124,25.1102001 53.14404,22.3070001 55.70494,20.2481001 C57.32204,18.9342001 59.52364,18.2771001 62.35354,18.2771001 L68.01384,18.2771001 L68.01384,10.3925001 L68.01354,10.3925001 Z M68.01354,22.8327001 L63.65594,22.8327001 C60.15224,22.8327001 58.04064,25.0667001 58.04064,28.7898001 C58.04064,32.6884001 60.19654,35.0537001 63.65594,35.0537001 L68.01354,35.0537001 L68.01354,22.8327001 Z"
        fill="#FFFFFF"
        fillRule="nonzero"
      />
    </g>
  </svg>
);

const TMDB_SVG = (
  <svg viewBox="0 0 273.42 35.52" width={70} height={9} aria-hidden={true} className="reference-links__tmdb-logo">
    <defs>
      <linearGradient id="tmdb-gradient" y1="17.76" x2="273.42" y2="17.76" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="#90cea1" />
        <stop offset="0.56" stopColor="#3cbec9" />
        <stop offset="1" stopColor="#00b3e5" />
      </linearGradient>
    </defs>
    <g>
      <path
        fill="url(#tmdb-gradient)"
        d="M191.85,35.37h63.9A17.67,17.67,0,0,0,273.42,17.7h0A17.67,17.67,0,0,0,255.75,0h-63.9A17.67,17.67,0,0,0,174.18,17.7h0A17.67,17.67,0,0,0,191.85,35.37ZM10.1,35.42h7.8V6.92H28V0H0v6.9H10.1Zm28.1,0H46V8.25h.1L55.05,35.4h6L70.3,8.25h.1V35.4h7.8V0H66.45l-8.2,23.1h-.1L50,0H38.2ZM89.14.12h11.7a33.56,33.56,0,0,1,8.08,1,18.52,18.52,0,0,1,6.67,3.08,15.09,15.09,0,0,1,4.53,5.52,18.5,18.5,0,0,1,1.67,8.25,16.91,16.91,0,0,1-1.62,7.58,16.3,16.3,0,0,1-4.38,5.5,19.24,19.24,0,0,1-6.35,3.37,24.53,24.53,0,0,1-7.55,1.15H89.14Zm7.8,28.2h4a21.66,21.66,0,0,0,5-.55A10.58,10.58,0,0,0,110,26a8.73,8.73,0,0,0,2.68-3.35,11.9,11.9,0,0,0,1-5.08,9.87,9.87,0,0,0-1-4.52,9.17,9.17,0,0,0-2.63-3.18A11.61,11.61,0,0,0,106.22,8a17.06,17.06,0,0,0-4.68-.63h-4.6ZM133.09.12h13.2a32.87,32.87,0,0,1,4.63.33,12.66,12.66,0,0,1,4.17,1.3,7.94,7.94,0,0,1,3,2.72,8.34,8.34,0,0,1,1.15,4.65,7.48,7.48,0,0,1-1.67,5,9.13,9.13,0,0,1-4.43,2.82V17a10.28,10.28,0,0,1,3.18,1,8.51,8.51,0,0,1,2.45,1.85,7.79,7.79,0,0,1,1.57,2.62,9.16,9.16,0,0,1,.55,3.2,8.52,8.52,0,0,1-1.2,4.68,9.32,9.32,0,0,1-3.1,3A13.38,13.38,0,0,1,152.32,35a22.5,22.5,0,0,1-4.73.5h-14.5Zm7.8,14.15h5.65a7.65,7.65,0,0,0,1.78-.2,4.78,4.78,0,0,0,1.57-.65,3.43,3.43,0,0,0,1.13-1.2,3.63,3.63,0,0,0,.42-1.8A3.3,3.3,0,0,0,151,8.6a3.42,3.42,0,0,0-1.23-1.13A6.07,6.07,0,0,0,148,6.9a9.9,9.9,0,0,0-1.85-.18h-5.3Zm0,14.65h7a8.27,8.27,0,0,0,1.83-.2,4.67,4.67,0,0,0,1.67-.7,3.93,3.93,0,0,0,1.23-1.3,3.8,3.8,0,0,0,.47-1.95,3.16,3.16,0,0,0-.62-2,4,4,0,0,0-1.58-1.18,8.23,8.23,0,0,0-2-.55,15.12,15.12,0,0,0-2.05-.15h-5.9Z"
      />
    </g>
  </svg>
);

export function ReferenceLinks({
  imdb_id,
  tvdb_id,
  tmdb_id,
  type,
}: ReferenceLinksProps) {
  const linkType = type === 'tv' || type === 'show' || type === 'episode' ? 'tv' : 'movie';

  const links: React.ReactNode[] = [];
  if (imdb_id?.trim()) {
    links.push(
      <a
        key="imdb"
        href={imdbUrl(imdb_id)}
        target="_blank"
        rel="noopener noreferrer"
        className="reference-links__link reference-links__link--imdb"
        aria-label="IMDB"
      >
        <img
          src={IMDB_LOGO_URL}
          alt=""
          aria-hidden
          className="reference-links__imdb-logo"
          width={32}
          height={16}
        />
      </a>,
    );
  }
  if (tvdb_id?.trim()) {
    links.push(
      <a
        key="tvdb"
        href={tvdbUrl(tvdb_id)}
        target="_blank"
        rel="noopener noreferrer"
        className="reference-links__link reference-links__link--tvdb"
        aria-label="TVDB"
      >
        {TVDB_SVG}
      </a>,
    );
  }
  if (tmdb_id?.trim()) {
    links.push(
      <a
        key="tmdb"
        href={tmdbUrl(tmdb_id, linkType)}
        target="_blank"
        rel="noopener noreferrer"
        className="reference-links__link reference-links__link--tmdb"
        aria-label="TMDB"
      >
        {TMDB_SVG}
      </a>,
    );
  }

  if (links.length === 0) return null;
  return <div className="reference-links">{links}</div>;
}
