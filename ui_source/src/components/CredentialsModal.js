import React, { useState } from 'react';
import {
  Modal,
  Box,
  SpaceBetween,
  Button,
  FormField,
  Input,
  Alert,
  Header,
  Container,
  ColumnLayout,
  Badge
} from '@cloudscape-design/components';

export default function CredentialsModal({ 
  visible, 
  onDismiss, 
  onConfirm, 
  selectedInstances, 
  actionType,
  loading 
}) {
  const [credentials, setCredentials] = useState({
    username: '',
    password: ''
  });
  const [errors, setErrors] = useState({});

  const validateCredentials = () => {
    const newErrors = {};
    
    if (!credentials.username.trim()) {
      newErrors.username = 'Username is required';
    }
    
    if (!credentials.password.trim()) {
      newErrors.password = 'Password is required';
    }
    
    if (credentials.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleConfirm = () => {
    if (validateCredentials()) {
      // Finding #5: hand the credentials to the parent, then immediately wipe
      // them from this component's state so they do not linger in memory after
      // submission.
      const submitted = { username: credentials.username, password: credentials.password };
      setCredentials({ username: '', password: '' });
      setErrors({});
      onConfirm(submitted);
    }
  };

  const handleDismiss = () => {
    setCredentials({ username: '', password: '' });
    setErrors({});
    onDismiss();
  };

  const actionTitle = actionType === 'precheck' ? 'Generate Precheck Report'
    : actionType === 'switchover' ? 'Blue/Green Switchover'
    : 'Database Upgrade';
  const actionDescription = actionType === 'precheck'
    ? 'Generate a comprehensive precheck report for the selected database instances'
    : actionType === 'switchover'
    ? 'Initiate the Blue/Green switchover for the selected database instances'
    : 'Initiate the upgrade process for the selected database instances';

  return (
    <Modal
      onDismiss={handleDismiss}
      visible={visible}
      size="medium"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss}>
              Cancel
            </Button>
            <Button 
              variant="primary" 
              onClick={handleConfirm}
              loading={loading}
            >
              {loading ? 'Processing...' : `Confirm ${actionType === 'precheck' ? 'Precheck' : actionType === 'switchover' ? 'Switchover' : 'Upgrade'}`}
            </Button>
          </SpaceBetween>
        </Box>
      }
      header={actionTitle}
    >
      <SpaceBetween direction="vertical" size="l">
        
        <Alert type="info">
          <strong>Action:</strong> {actionDescription}
        </Alert>

        <Container header={<Header variant="h3">Selected Instances ({selectedInstances.length})</Header>}>
          <SpaceBetween direction="vertical" size="s">
            {selectedInstances.slice(0, 5).map((instance, index) => (
              <Box key={instance.id}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <strong>{instance.database_name}</strong>
                  <Badge color={instance.cluster_type === 'RDS' ? 'green' : 'blue'}>
                    {instance.cluster_type}
                  </Badge>
                  <span style={{ color: '#5f6b7a', fontSize: '14px' }}>
                    {instance.region}
                  </span>
                </div>
                <div style={{ fontSize: '12px', color: '#879596', marginTop: '2px' }}>
                  {instance.rds_instance} → {instance.target_engine_version}
                </div>
              </Box>
            ))}
            {selectedInstances.length > 5 && (
              <Box>
                <em>... and {selectedInstances.length - 5} more instances</em>
              </Box>
            )}
          </SpaceBetween>
        </Container>

        <Container header={<Header variant="h3">Database Credentials</Header>}>
          <SpaceBetween direction="vertical" size="m">
            <Alert type="warning">
              <strong>Security Notice:</strong> Credentials are transmitted over HTTPS to
              AWS Secrets Manager, where they are stored for database operations. They are
              held only transiently in the browser to submit this request and are cleared
              from memory immediately afterward. Ensure you have the necessary permissions
              to perform database operations.
            </Alert>

            <ColumnLayout columns={1}>
              <FormField
                label="Master Username"
                description="Database master username for authentication"
                errorText={errors.username}
              >
                <Input
                  value={credentials.username}
                  onChange={({ detail }) => {
                    setCredentials(prev => ({ ...prev, username: detail.value }));
                    if (errors.username) {
                      setErrors(prev => ({ ...prev, username: '' }));
                    }
                  }}
                  placeholder="Enter database master username"
                  invalid={!!errors.username}
                />
              </FormField>

              <FormField
                label="Master Password"
                description="Database master password for authentication"
                errorText={errors.password}
              >
                <Input
                  value={credentials.password}
                  onChange={({ detail }) => {
                    setCredentials(prev => ({ ...prev, password: detail.value }));
                    if (errors.password) {
                      setErrors(prev => ({ ...prev, password: '' }));
                    }
                  }}
                  placeholder="Enter database master password"
                  type="password"
                  invalid={!!errors.password}
                />
              </FormField>
            </ColumnLayout>
          </SpaceBetween>
        </Container>

        {actionType === 'precheck' ? (
          <Alert type="info">
            <strong>Precheck Report will include:</strong>
            <ul style={{ marginTop: '8px', marginBottom: '0' }}>
              <li>Current database version and compatibility analysis</li>
              <li>Parameter group validation and recommendations</li>
              <li>Storage and performance requirements assessment</li>
              <li>Backup and snapshot status verification</li>
              <li>Potential upgrade issues and mitigation strategies</li>
              <li>Step-by-step upgrade recommendations</li>
            </ul>
          </Alert>
        ) : actionType === 'switchover' ? (
          <Alert type="warning">
            <strong>Switchover Warning:</strong> This will perform a Blue/Green switchover.
            Ensure you have:
            <ul style={{ marginTop: '8px', marginBottom: '0' }}>
              <li>Verified the green environment is healthy and in sync</li>
              <li>Notified application teams of the upcoming switchover</li>
              <li>Confirmed replication lag is near zero</li>
              <li>Prepared rollback procedures in case of failure</li>
            </ul>
          </Alert>
        ) : (
          <Alert type="warning">
            <strong>Important:</strong> This action will initiate the database upgrade process.
            Ensure you have:
            <ul style={{ marginTop: '8px', marginBottom: '0' }}>
              <li>Created recent backups or snapshots</li>
              <li>Reviewed the precheck report</li>
              <li>Planned for application downtime</li>
              <li>Verified rollback procedures</li>
            </ul>
          </Alert>
        )}

      </SpaceBetween>
    </Modal>
  );
}
