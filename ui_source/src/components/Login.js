import React, { useState } from 'react';
import {
  Box,
  Container,
  Header,
  SpaceBetween,
  FormField,
  Input,
  Button,
  Alert,
} from '@cloudscape-design/components';
import { signIn, completeNewPassword } from '../services/auth';

// Finding #1 (frontend): login gate. The app is not rendered until the user
// authenticates against the Cognito User Pool that protects the API.
export default function Login({ onSignedIn }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [challengeUser, setChallengeUser] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSignIn = async () => {
    setError('');
    setLoading(true);
    try {
      const result = await signIn(username.trim(), password);
      if (result.status === 'NEW_PASSWORD_REQUIRED') {
        setChallengeUser(result.user);
      } else {
        onSignedIn();
      }
    } catch (err) {
      setError(err.message || 'Sign-in failed. Check your credentials and try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleNewPassword = async () => {
    setError('');
    setLoading(true);
    try {
      await completeNewPassword(challengeUser, newPassword);
      onSignedIn();
    } catch (err) {
      setError(err.message || 'Could not set new password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box padding={{ top: 'xxl' }} textAlign="center">
      <Box display="inline-block" width="420px">
        <Container header={<Header variant="h1">MySQL Upgrade Accelerator</Header>}>
          <SpaceBetween direction="vertical" size="l">
            {error && <Alert type="error">{error}</Alert>}

            {!challengeUser ? (
              <SpaceBetween direction="vertical" size="m">
                <FormField label="Username or email">
                  <Input
                    value={username}
                    onChange={({ detail }) => setUsername(detail.value)}
                    placeholder="Enter your username"
                    onKeyDown={({ detail }) => { if (detail.key === 'Enter') handleSignIn(); }}
                  />
                </FormField>
                <FormField label="Password">
                  <Input
                    type="password"
                    value={password}
                    onChange={({ detail }) => setPassword(detail.value)}
                    placeholder="Enter your password"
                    onKeyDown={({ detail }) => { if (detail.key === 'Enter') handleSignIn(); }}
                  />
                </FormField>
                <Button variant="primary" loading={loading} onClick={handleSignIn}>
                  Sign in
                </Button>
              </SpaceBetween>
            ) : (
              <SpaceBetween direction="vertical" size="m">
                <Alert type="info">
                  First sign-in: please choose a new password.
                </Alert>
                <FormField label="New password">
                  <Input
                    type="password"
                    value={newPassword}
                    onChange={({ detail }) => setNewPassword(detail.value)}
                    placeholder="Enter a new password"
                    onKeyDown={({ detail }) => { if (detail.key === 'Enter') handleNewPassword(); }}
                  />
                </FormField>
                <Button variant="primary" loading={loading} onClick={handleNewPassword}>
                  Set password and continue
                </Button>
              </SpaceBetween>
            )}
          </SpaceBetween>
        </Container>
      </Box>
    </Box>
  );
}
