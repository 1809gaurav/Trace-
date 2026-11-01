import React from 'react';
import { StrictMode } from 'react';
import * as ReactDOM from 'react-dom';
import { createRoot } from 'react-dom/client';
import '@fontsource/atkinson-hyperlegible/400.css';
import '@fontsource/atkinson-hyperlegible/700.css';
import '@fontsource/lexend/600.css';
import '@fontsource/lexend/700.css';
import '@fontsource/jetbrains-mono/400.css';
import './index.css';
import App from './App.tsx';

if (import.meta.env.DEV) {
  void import('@axe-core/react').then(({ default: axe }) => {
    axe(React, ReactDOM, 1000);
  });
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
