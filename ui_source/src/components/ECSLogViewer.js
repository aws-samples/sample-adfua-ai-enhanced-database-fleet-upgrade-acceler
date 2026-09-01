import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { getApiBase } from '../config';
import {
  Modal,
  Box,
  SpaceBetween,
  Button,
  Header,
  StatusIndicator,
  Badge,
} from '@cloudscape-design/components';

const POLL_INTERVAL_MS = 5000;

const STATUS_COLOR = {
  PROVISIONING: 'blue',
  PENDING:      'blue',
  RUNNING:      'green',
  DEPROVISIONING: 'blue',
  STOPPED:      'grey',
  UNKNOWN:      'grey',
};

const ECSLogViewer = ({ visible, onDismiss, taskArn, clusterName, taskType = 'prechecker' }) => {
  const API_BASE = getApiBase();
  const [logs, setLogs]           = useState([]);
  const [taskStatus, setTaskStatus] = useState('');
  const [stopReason, setStopReason] = useState('');
  const [exitCode, setExitCode]   = useState(null);
  const [logExists, setLogExists] = useState(true);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const nextTokenRef = useRef(null);
  const logEndRef    = useRef(null);
  const intervalRef  = useRef(null);

  const scrollToBottom = () => logEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const fetchLogs = useCallback(async () => {
    if (!taskArn) return;
    setLoading(true);
    try {
      const resp = await axios.post(`${API_BASE}/task-logs`, {
        task_arn:   taskArn,
        task_type:  taskType,
        next_token: nextTokenRef.current,
      });

      const data = typeof resp.data.body === 'string'
        ? JSON.parse(resp.data.body)
        : resp.data;

      setTaskStatus(data.task_status || '');
      setStopReason(data.stop_reason || '');
      setExitCode(data.exit_code ?? null);
      setLogExists(data.log_exists !== false);

      if (data.events && data.events.length > 0) {
        setLogs(prev => {
          const existing = new Set(prev.map(l => `${l.timestamp}${l.message}`));
          const fresh = data.events.filter(e => !existing.has(`${e.timestamp}${e.message}`));
          return [...prev, ...fresh];
        });
        nextTokenRef.current = data.next_token;
      }

      // Stop polling once task is done
      if (['STOPPED', 'DEPROVISIONING'].includes(data.task_status)) {
        clearInterval(intervalRef.current);
      }
    } catch (err) {
      setError(`Failed to fetch logs: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [taskArn, taskType]);

  // Start polling when modal opens
  useEffect(() => {
    if (visible && taskArn) {
      setLogs([]);
      setError('');
      setTaskStatus('');
      setStopReason('');
      setExitCode(null);
      nextTokenRef.current = null;

      fetchLogs();
      intervalRef.current = setInterval(fetchLogs, POLL_INTERVAL_MS);
    }
    return () => clearInterval(intervalRef.current);
  }, [visible, taskArn]);

  useEffect(() => { scrollToBottom(); }, [logs]);

  const statusType = () => {
    if (taskStatus === 'RUNNING')  return 'success';
    if (taskStatus === 'STOPPED')  return exitCode === 0 ? 'success' : 'error';
    if (['PROVISIONING', 'PENDING'].includes(taskStatus)) return 'loading';
    return 'pending';
  };

  const statusLabel = () => {
    if (taskStatus === 'STOPPED' && exitCode !== null) {
      return `${taskStatus} (exit ${exitCode})`;
    }
    return taskStatus || 'Waiting...';
  };

  return (
    <Modal
      onDismiss={onDismiss}
      visible={visible}
      closeAriaLabel="Close"
      size="max"
      header={
        <Header
          variant="h2"
          description={`Task: ${taskArn?.split('/').pop() || ''}`}
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <StatusIndicator type={statusType()}>{statusLabel()}</StatusIndicator>
              <Button onClick={fetchLogs} loading={loading} iconName="refresh">Refresh</Button>
            </SpaceBetween>
          }
        >
          ECS Task Logs — {taskType === 'prechecker' ? 'Precheck' : taskType === 'switchover' ? 'Switchover' : 'Upgrade'}
        </Header>
      }
    >
      <SpaceBetween direction="vertical" size="m">

        {/* Stop reason banner */}
        {stopReason && (
          <Box color={exitCode === 0 ? 'text-status-success' : 'text-status-error'}>
            {exitCode === 0 ? '✅' : '❌'} {stopReason}
          </Box>
        )}

        {/* Log terminal */}
        <div style={{
          background: '#0d1117',
          color: '#c9d1d9',
          padding: '16px',
          borderRadius: '6px',
          fontFamily: '"Courier New", monospace',
          fontSize: '12px',
          lineHeight: '1.6',
          height: '520px',
          overflowY: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}>
          {error && (
            <div style={{ color: '#ff7b72', marginBottom: '8px' }}>❌ {error}</div>
          )}
          {!logExists && (
            <div style={{ color: '#8b949e' }}>
              Log stream not yet available — task is still starting up...
            </div>
          )}
          {logExists && logs.length === 0 && !error && (
            <div style={{ color: '#8b949e' }}>
              ⏳ Waiting for logs... task status: {taskStatus || 'checking'}
            </div>
          )}
          {logs.map((log, i) => {
            const ts  = new Date(log.timestamp).toISOString().replace('T', ' ').slice(0, 19);
            const msg = log.message.trimEnd();
            const isError = /error|exception|failed|traceback/i.test(msg);
            const isWarn  = /warn|warning/i.test(msg);
            return (
              <div key={i} style={{ marginBottom: '1px' }}>
                <span style={{ color: '#6e7681' }}>{ts} </span>
                <span style={{ color: isError ? '#ff7b72' : isWarn ? '#e3b341' : '#c9d1d9' }}>
                  {msg}
                </span>
              </div>
            );
          })}
          <div ref={logEndRef} />
        </div>

        <Box float="right">
          <Button onClick={onDismiss} variant="primary">Close</Button>
        </Box>
      </SpaceBetween>
    </Modal>
  );
};

export default ECSLogViewer;
