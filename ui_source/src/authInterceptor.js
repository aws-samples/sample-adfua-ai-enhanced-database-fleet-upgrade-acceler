// Global axios request interceptor.
//
// Finding #1 (frontend): every request to the API base is now sent with an
// Authorization: Bearer <Cognito ID token> header so it passes the API Gateway
// Cognito authorizer. Registering a single global interceptor covers all axios
// callers (App.js, services, and components) without editing each call site.

import axios from 'axios';
import { getApiBase } from './config';
import { getIdToken, signOut } from './services/auth';

let _installed = false;

export function installAuthInterceptor() {
  if (_installed) return;
  _installed = true;

  axios.interceptors.request.use(async (config) => {
    try {
      const apiBase = getApiBase();
      const url = config.url || '';
      // Only attach the token to calls targeting our API (avoid leaking the
      // JWT to any third-party endpoint).
      const targetsApi = apiBase && (url.startsWith(apiBase) || url.startsWith('/'));
      if (targetsApi) {
        const token = await getIdToken();
        if (token) {
          config.headers = config.headers || {};
          config.headers.Authorization = `Bearer ${token}`;
        }
      }
    } catch (e) {
      // If token retrieval fails, let the request proceed and fail with 401.
    }
    return config;
  });

  // On a 401 the session is invalid/expired — clear it so the app returns to
  // the login screen.
  axios.interceptors.response.use(
    (resp) => resp,
    (error) => {
      if (error?.response?.status === 401) {
        signOut();
      }
      return Promise.reject(error);
    }
  );
}
