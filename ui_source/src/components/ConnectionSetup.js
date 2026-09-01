import React, { useState } from 'react';
import Papa from 'papaparse';
import axios from 'axios';
import { getApiBase } from '../config';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  FormField,
  Input,
  FileUpload,
  Table,
  Box,
  Alert,
  StatusIndicator,
  ColumnLayout,
  Badge,
} from '@cloudscape-design/components';

export default function ConfigGenerator() {
  const API_BASE = getApiBase();

  const STATUS_CONFIG = {
    idle:            { type: 'pending', label: 'Not configured' },
    testing:         { type: 'loading', label: 'Configuring...' },
    configured:      { type: 'success', label: 'Configured' },
    already_exists:  { type: 'warning', label: 'BG Active' },
    error:           { type: 'error',   label: 'Error' },
  };
  const [file,        setFile]        = useState([]);
  const [instances,   setInstances]   = useState([]);
  const [username,    setUsername]    = useState('');
  const [password,    setPassword]    = useState('');
  const [results,     setResults]     = useState({});   // keyed by database_name
  const [loading,     setLoading]     = useState(false);
  const [globalError, setGlobalError] = useState('');
  const [globalOk,    setGlobalOk]    = useState('');

  // ── CSV parse ─────────────────────────────────────────────────────────────
  const handleFileUpload = ({ value }) => {
    setFile(value);
    setInstances([]);
    setResults({});
    if (!value.length) return;

    Papa.parse(value[0], {
      header: true,
      skipEmptyLines: true,
      complete: ({ data, errors }) => {
        if (errors.length) { setGlobalError('CSV parse error: ' + errors[0].message); return; }
        setInstances(data.map((row, i) => ({
          id:                     i.toString(),
          database_name:          row.database_name          || '',
          cluster_type:           row.cluster_type           || 'rds',
          region:                 row.region                 || 'us-east-1',
          rds_instance:           row.rds_instance           || '',
          aurora_cluster:         row.aurora_cluster         || '',
          target_parameter_family: row.target_parameter_family || '',
          target_engine_version:  row.target_engine_version  || '',
          credentials_secret_name: row.credentials_secret_name || '',
        })));
        setGlobalOk(`Loaded ${data.length} instance(s) from CSV`);
      },
      error: (e) => setGlobalError('Error reading file: ' + e.message),
    });
  };

  // ── Test connection ───────────────────────────────────────────────────────
  const handleConfigGenerate = async () => {
    if (!instances.length)  { setGlobalError('Upload a CSV first'); return; }
    if (!username)          { setGlobalError('Enter a database username'); return; }
    if (!password)          { setGlobalError('Enter a database password'); return; }

    setLoading(true);
    setGlobalError('');
    setGlobalOk('');

    // Mark all as testing
    const testing = {};
    instances.forEach(i => { testing[i.database_name] = { status: 'testing' }; });
    setResults(testing);

    try {
      const resp = await axios.post(`${API_BASE}/test-connection`, {
        instances,
        username,
        password,
      }, { timeout: 30000 });

      const data = typeof resp.data.body === 'string'
        ? JSON.parse(resp.data.body)
        : resp.data;

      const newResults = {};
      data.results.forEach(r => { newResults[r.database_name] = r; });
      setResults(newResults);

      const ok   = data.results.filter(r => r.status === 'configured').length;
      const fail = data.results.filter(r => r.status === 'error').length;
      const bgExists = data.results.filter(r => r.status === 'already_exists');
      if (bgExists.length > 0 && fail === 0 && ok === 0) {
        setGlobalError(`⚠️ ${bgExists.map(r => `${r.database_name}: ${r.message}`).join(' | ')}`);
      } else if (fail === 0 && bgExists.length === 0) {
        setGlobalOk(`✅ ${ok} instance(s) configured. Credentials saved. Ready for precheck.`);
      } else if (fail === 0 && bgExists.length > 0) {
        setGlobalOk(`✅ ${ok} instance(s) configured. ⚠️ ${bgExists.length} instance(s) already have Blue/Green deployment active.`);
      } else {
        setGlobalError(`❌ ${fail} error(s). Check details below.`);
      }
    } catch (e) {
      setGlobalError('API error: ' + (e.response?.data?.message || e.message));
      const errResults = {};
      instances.forEach(i => {
        errResults[i.database_name] = { status: 'error', error: e.message };
      });
      setResults(errResults);
    } finally {
      setLoading(false);
    }
  };

  // ── Table columns ─────────────────────────────────────────────────────────
  const columns = [
    {
      id: 'database_name',
      header: 'Database',
      cell: item => (
        <SpaceBetween direction="horizontal" size="xs">
          <strong>{item.database_name}</strong>
          <Badge color={item.cluster_type?.toLowerCase() === 'aurora' ? 'blue' : 'green'}>
            {item.cluster_type}
          </Badge>
        </SpaceBetween>
      ),
    },
    { id: 'rds_instance', header: 'Instance / Cluster',
      cell: item => item.rds_instance || item.aurora_cluster || '—' },
    { id: 'region', header: 'Region', cell: item => item.region },
    {
      id: 'status',
      header: 'Config Status',
      cell: item => {
        const r   = results[item.database_name];
        const cfg = STATUS_CONFIG[r?.status || 'idle'];
        return (
          <SpaceBetween direction="vertical" size="xxs">
            <StatusIndicator type={cfg.type}>{cfg.label}</StatusIndicator>
            {r?.status === 'configured' && (
              <Box fontSize="body-s" color="text-status-success">
                {r.host}:{r.port} · Secret: {r.secret_name} ({r.secret_action})
              </Box>
            )}
            {r?.status === 'already_exists' && (
              <Box fontSize="body-s" color="text-status-warning">{r.message}</Box>
            )}
            {r?.status === 'error' && (
              <Box fontSize="body-s" color="text-status-error">{r.error}</Box>
            )}
          </SpaceBetween>
        );
      },
    },
  ];

  const allConnected = instances.length > 0 &&
    instances.every(i => results[i.database_name]?.status === 'configured');

  return (
    <SpaceBetween direction="vertical" size="l">

      {globalError && (
        <Alert type="error" dismissible onDismiss={() => setGlobalError('')}>
          {globalError}
        </Alert>
      )}
      {globalOk && (
        <Alert type="success" dismissible onDismiss={() => setGlobalOk('')}>
          {globalOk}
        </Alert>
      )}

      {/* Step 1 — Upload CSV */}
      <Container header={<Header variant="h2" counter="1">Upload CSV</Header>}>
        <FormField
          label="Instance configuration CSV"
          description="Same CSV format used on the main page — database_name, cluster_type, region, rds_instance, target_parameter_family, target_engine_version"
        >
          <FileUpload
            onChange={({ detail }) => handleFileUpload(detail)}
            value={file}
            accept=".csv"
            i18nStrings={{
              uploadButtonText: e => e ? 'Choose files' : 'Choose file',
              dropzoneText:     e => e ? 'Drop files'  : 'Drop file',
              removeFileAriaLabel: e => `Remove file ${e + 1}`,
              limitShowFewer: 'Show fewer', limitShowMore: 'Show more',
              errorIconAriaLabel: 'Error',
            }}
            constraintText="CSV files only"
          />
        </FormField>
      </Container>

      {/* Step 2 — Credentials */}
      {instances.length > 0 && (
        <Container header={<Header variant="h2" counter="2">Database Credentials</Header>}>
          <SpaceBetween direction="vertical" size="m">
            <Box>
              These credentials will be stored securely in AWS Secrets Manager.
              The precheck and upgrade ECS tasks will read them from there —
              you will not need to enter them again.
            </Box>
            <ColumnLayout columns={2}>
              <FormField label="Username">
                <Input
                  value={username}
                  onChange={({ detail }) => setUsername(detail.value)}
                  placeholder="admin"
                  type="text"
                />
              </FormField>
              <FormField label="Password">
                <Input
                  value={password}
                  onChange={({ detail }) => setPassword(detail.value)}
                  placeholder="••••••••"
                  type="password"
                />
              </FormField>
            </ColumnLayout>
            <Box>
              <Button
                variant="primary"
                onClick={handleConfigGenerate}
                loading={loading}
                disabled={!username || !password || loading}
                iconName="settings"
              >
                {loading ? 'Configuring...' : `Generate Config (${instances.length})`}
              </Button>
            </Box>
          </SpaceBetween>
        </Container>
      )}

      {/* Step 3 — Results */}
      {instances.length > 0 && (
        <Container
          header={
            <Header
              variant="h2"
              counter="3"
              description="Connection status per instance. Successful connections have credentials saved to Secrets Manager."
            >
              Config Results
            </Header>
          }
        >
          <SpaceBetween direction="vertical" size="m">
            <Table
              columnDefinitions={columns}
              items={instances}
              trackBy="id"
              empty={<Box textAlign="center">No instances loaded</Box>}
            />
            {allConnected && (
              <Alert type="success" header="All instances configured">
                Credentials saved to Secrets Manager and network configured.
                You can now go to <strong>Upload Configuration</strong> and run the precheck.
              </Alert>
            )}
          </SpaceBetween>
        </Container>
      )}

    </SpaceBetween>
  );
}
