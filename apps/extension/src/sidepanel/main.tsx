import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../shared/ui/styles.css';
import './sidepanel.css';
import { App } from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
