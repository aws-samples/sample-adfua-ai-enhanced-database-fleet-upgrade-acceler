import React from 'react';
import {
  Modal,
  Box,
  SpaceBetween,
  Button,
  Header,
  Container,
  Badge,
  Icon,
  Cards,
  Alert
} from '@cloudscape-design/components';

export default function PrecheckResultsModal({ 
  visible, 
  onDismiss, 
  selectedInstances,
  precheckResponse 
}) {
  const results = precheckResponse?.results || [];

  // Separate results by status
  const bgExistsResults = results.filter(r => r.status === 'already_exists');
  const startedResults = results.filter(r => r.status === 'started');
  const errorResults = results.filter(r => r.status === 'error');

  // Generate report locations only for started instances
  const reportLocations = startedResults.map(r => {
    const instance = selectedInstances.find(i => i.database_name === r.database_name);
    return {
      database_name: r.database_name,
      region: instance?.region || 'us-east-1',
      config_location: r.config_s3_path || `s3://${instance?.bucket_name}/config/${r.database_name}.ini`,
      report_location: r.report_s3_path || `s3://${instance?.bucket_name}/precheck_report/${r.database_name}-precheck-report.html`
    };
  });

  return (
    <Modal
      onDismiss={onDismiss}
      visible={visible}
      size="large"
      footer={
        <Box float="right">
          <Button variant="primary" onClick={onDismiss}>
            Close
          </Button>
        </Box>
      }
      header="Precheck Results"
    >
      <SpaceBetween direction="vertical" size="l">

        {/* BG Already Exists - show warning messages */}
        {bgExistsResults.length > 0 && (
          <Container
            header={
              <Header variant="h3">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Icon name="status-warning" />
                  Blue/Green Deployment Already Active
                </div>
              </Header>
            }
          >
            <SpaceBetween direction="vertical" size="s">
              {bgExistsResults.map((r, idx) => (
                <Alert key={idx} type="warning" header={r.database_name}>
                  {r.message}
                  {r.deployment_id && (
                    <Box variant="small" margin={{ top: 'xs' }}>
                      Deployment ID: <code>{r.deployment_id}</code>
                    </Box>
                  )}
                </Alert>
              ))}
            </SpaceBetween>
          </Container>
        )}

        {/* Error Results */}
        {errorResults.length > 0 && (
          <Container
            header={
              <Header variant="h3">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Icon name="status-negative" />
                  Errors
                </div>
              </Header>
            }
          >
            <SpaceBetween direction="vertical" size="s">
              {errorResults.map((r, idx) => (
                <Alert key={idx} type="error" header={r.database_name}>
                  {r.error || 'An unknown error occurred.'}
                </Alert>
              ))}
            </SpaceBetween>
          </Container>
        )}

        {/* Report Storage Locations - only for successfully started tasks */}
        {startedResults.length > 0 && (
          <Container 
            header={
              <Header variant="h3" description="Your precheck reports will be available at the following S3 locations">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Icon name="folder" />
                  Report Storage Locations
                </div>
              </Header>
            }
          >
            <Cards
              cardDefinition={{
                header: item => (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Icon name="file" />
                    <strong>{item.database_name}</strong>
                    <Badge color="blue">S3</Badge>
                    <Badge color={item.region === 'us-east-1' ? 'green' : 'grey'}>
                      {item.region}
                    </Badge>
                  </div>
                ),
                sections: [
                  {
                    id: "config",
                    header: "Configuration File",
                    content: item => (
                      <Box>
                        <div style={{ 
                          fontFamily: 'Monaco, Consolas, monospace', 
                          fontSize: '12px', 
                          backgroundColor: '#f8f9fa', 
                          padding: '8px', 
                          borderRadius: '4px',
                          border: '1px solid #e1e4e8',
                          wordBreak: 'break-all'
                        }}>
                          {item.config_location}
                        </div>
                      </Box>
                    )
                  },
                  {
                    id: "report",
                    header: "HTML Report (Available after completion)",
                    content: item => (
                      <Box>
                        <div style={{ 
                          fontFamily: 'Monaco, Consolas, monospace', 
                          fontSize: '12px', 
                          backgroundColor: '#f8f9fa', 
                          padding: '8px', 
                          borderRadius: '4px',
                          border: '1px solid #e1e4e8',
                          wordBreak: 'break-all'
                        }}>
                          {item.report_location}
                        </div>
                      </Box>
                    )
                  }
                ]
              }}
              cardsPerRow={[
                { cards: 1 },
                { minWidth: 500, cards: 2 }
              ]}
              items={reportLocations}
              loadingText="Loading report locations"
              empty={
                <Box textAlign="center" color="inherit">
                  <b>No instances processed</b>
                  <Box variant="p" color="inherit">
                    No database instances were processed.
                  </Box>
                </Box>
              }
            />
          </Container>
        )}

        {/* If everything is either bg_exists or error and nothing started */}
        {startedResults.length === 0 && bgExistsResults.length === 0 && errorResults.length === 0 && (
          <Alert type="info">
            No precheck tasks were initiated. Please select instances and try again.
          </Alert>
        )}

      </SpaceBetween>
    </Modal>
  );
}
