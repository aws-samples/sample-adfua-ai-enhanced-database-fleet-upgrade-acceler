import React from 'react';
import ReactDOM from 'react-dom/client';
import '@cloudscape-design/global-styles/index.css';
import './index.css';
import App from './App';
import { loadConfig } from './config';
import { installAuthInterceptor } from './authInterceptor';

// Finding #6: strip debug logging from production builds. In production we
// silence console.log/debug/info (which dumped instance lists, DB names, and
// full API/error responses) while preserving warn/error for real diagnostics.
if (process.env.NODE_ENV === 'production') {
  const noop = () => {};
  console.log = noop;
  console.debug = noop;
  console.info = noop;
}

loadConfig().then(() => {
  installAuthInterceptor();
  const root = ReactDOM.createRoot(document.getElementById('root'));
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
