// components/SearchBar.tsx

import React, { useState } from 'react';
import TextField from '@mui/material/TextField';
import styles from './MediaItems.module.css';


interface SearchBarProps {
  onSearch: (query: string) => void;
}

const MediaItemsSearchBar: React.FC<SearchBarProps> = ({ onSearch }) => {
  const [query, setQuery] = useState('');

  const handleSearch = (event: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(event.target.value);
    onSearch(event.target.value);
  };

  return (
    <TextField
      className={styles.searchBar}
      label="Search"
      variant="outlined"
      value={query}
      onChange={handleSearch}
      fullWidth
    />
  );
}

export default MediaItemsSearchBar;
