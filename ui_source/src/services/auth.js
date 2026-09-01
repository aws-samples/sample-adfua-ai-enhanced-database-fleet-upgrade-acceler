// Cognito authentication service.
//
// Finding #1 (frontend): the API is now protected by a Cognito User Pool
// authorizer. This module handles sign-in, session retrieval, token refresh,
// and sign-out using amazon-cognito-identity-js. The ID token it produces is
// attached to every API request by src/authInterceptor.js.

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
} from 'amazon-cognito-identity-js';
import { getUserPoolId, getUserPoolClientId } from '../config';

let _pool = null;

function getPool() {
  if (_pool) return _pool;
  const UserPoolId = getUserPoolId();
  const ClientId = getUserPoolClientId();
  if (!UserPoolId || !ClientId) {
    throw new Error('Cognito is not configured (missing user pool id/client id).');
  }
  _pool = new CognitoUserPool({ UserPoolId, ClientId });
  return _pool;
}

export function isAuthConfigured() {
  return Boolean(getUserPoolId() && getUserPoolClientId());
}

/**
 * Sign in with username/password.
 * Resolves with { status: 'SUCCESS' } or { status: 'NEW_PASSWORD_REQUIRED', user }.
 */
export function signIn(username, password) {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: username, Pool: getPool() });
    const authDetails = new AuthenticationDetails({ Username: username, Password: password });
    user.authenticateUser(authDetails, {
      onSuccess: () => resolve({ status: 'SUCCESS' }),
      onFailure: (err) => reject(err),
      newPasswordRequired: () => resolve({ status: 'NEW_PASSWORD_REQUIRED', user }),
    });
  });
}

/**
 * Complete the NEW_PASSWORD_REQUIRED challenge for first-login users.
 */
export function completeNewPassword(user, newPassword) {
  return new Promise((resolve, reject) => {
    user.completeNewPasswordChallenge(newPassword, {}, {
      onSuccess: () => resolve({ status: 'SUCCESS' }),
      onFailure: (err) => reject(err),
    });
  });
}

/**
 * Return a valid (auto-refreshed) session for the current user, or null.
 */
export function getSession() {
  return new Promise((resolve) => {
    let user;
    try {
      user = getPool().getCurrentUser();
    } catch (e) {
      resolve(null);
      return;
    }
    if (!user) {
      resolve(null);
      return;
    }
    user.getSession((err, session) => {
      if (err || !session || !session.isValid()) {
        resolve(null);
        return;
      }
      resolve(session);
    });
  });
}

/**
 * Return the current ID token (JWT) as a string, or null if not signed in.
 * amazon-cognito-identity-js refreshes the session automatically when needed.
 */
export async function getIdToken() {
  const session = await getSession();
  return session ? session.getIdToken().getJwtToken() : null;
}

export async function getCurrentUsername() {
  try {
    const user = getPool().getCurrentUser();
    return user ? user.getUsername() : null;
  } catch (e) {
    return null;
  }
}

export function signOut() {
  try {
    const user = getPool().getCurrentUser();
    if (user) user.signOut();
  } catch (e) {
    // no-op
  }
}
