export type Item = {
    download_tries?: any;
    file_name?: any;
    guid?: any;
    ids?: {
      imdb?: any | null;
      tmdb?: any | null;
      tvdb?: any | null;
    };
    key?: any;
    library_section?: any | null;
    scrape_tries?: any;
    scraped_at?: any;
    state: any;
    streams?: any;
    title: any;
    type: any;
    year: any;
  };

export type MediaItemCardProps = {
    title: string;
    items: Item[];
  };
