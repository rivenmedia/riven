// routes/Routing.tsx
import React from 'react';
import { Route, Routes } from 'react-router-dom';

// import ConsolePage from '../components/ConsolePage';
import MediaPage from '../pages/MediaPage';
import Dashboard from '../pages/Dashboard';
import ConsolePage from '../pages/ConsolePage';
import SettingsPage from '../pages/SettingsPage';
import HomePage from '../pages/HomePage';
// import SettingsPage from '../components/ContentPage';

const Routing: React.FC = () => {
  return (
    <Routes>
      <Route path="/console" element={<Dashboard PageComponent={ConsolePage}/>}  />
      <Route path="/settings" element={<Dashboard PageComponent={SettingsPage}/>}  />
      <Route path="/media" element={<Dashboard PageComponent={MediaPage}/>} />
      <Route path="/" element={<Dashboard PageComponent={HomePage}/>} />
    </Routes>
  );
};

export default Routing;
