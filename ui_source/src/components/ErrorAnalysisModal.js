import React from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Modal,
  Box,
  SpaceBetween,
  Button,
  Header,
  Container,
  Badge,
  Icon
} from '@cloudscape-design/components';

export default function ErrorAnalysisModal({ 
  visible, 
  onDismiss, 
  analysisData 
}) {
  if (!analysisData) return null;

  const cleanAnalysisText = (rawText) => {
    if (!rawText) return '';
    return rawText
      .replace(/\n\s*\n\s*\n/g, '\n\n')
      .replace(/\n{4,}/g, '\n\n')
      .trim();
  };

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
      header="AI Error Analysis"
    >
      <SpaceBetween direction="vertical" size="l">
        
        <Container 
          header={
            <Header 
              variant="h3" 
              description="Bedrock Claude 3 analysis of upgrade error logs"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Icon name="status-warning" />
                Error Log Analysis
                <Badge color="blue">AI Powered</Badge>
              </div>
            </Header>
          }
        >
          <SpaceBetween direction="vertical" size="m">
            
            {analysisData.error_count && (
              <Box>
                <strong>Errors Found:</strong> {analysisData.error_count}
              </Box>
            )}
            
            <Box>
              <div style={{ 
                backgroundColor: '#fff3cd', 
                padding: '12px', 
                borderRadius: '6px',
                border: '1px solid #ffeaa7',
                marginBottom: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <Icon name="status-warning" />
                <span style={{ fontSize: '14px', color: '#856404' }}>
                  <strong>Disclaimer:</strong> This analysis is AI-generated and may contain inaccuracies. Please verify findings independently.
                </span>
              </div>
              
              <div style={{ 
                backgroundColor: '#1e1e1e',
                color: '#f8f8f2',
                padding: '20px', 
                borderRadius: '8px',
                border: '1px solid #444',
                fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
                fontSize: '14px',
                lineHeight: '1.6',
                overflow: 'auto',
                maxHeight: '70vh'
              }}>
                <ReactMarkdown
                  components={{
                    h1: ({ children }) => (
                      <h1 style={{ color: '#60a5fa', fontSize: '20px', fontWeight: 'bold', margin: '20px 0 10px 0', borderBottom: '2px solid #3b82f6', paddingBottom: '8px' }}>{children}</h1>
                    ),
                    h2: ({ children }) => (
                      <h2 style={{ color: '#34d399', fontSize: '16px', fontWeight: 'bold', margin: '16px 0 8px 0' }}>{children}</h2>
                    ),
                    h3: ({ children }) => (
                      <h3 style={{ color: '#fbbf24', fontSize: '14px', fontWeight: 'bold', margin: '12px 0 6px 0' }}>{children}</h3>
                    ),
                    code: ({ inline, children }) => (
                      inline 
                        ? <code style={{ background: '#374151', padding: '2px 4px', borderRadius: '3px', fontFamily: 'Monaco, Consolas, monospace', fontSize: '12px', color: '#fde68a', border: '1px solid #4b5563' }}>{children}</code>
                        : <pre style={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '6px', padding: '12px', margin: '8px 0', fontFamily: 'Monaco, Consolas, monospace', fontSize: '12px', color: '#d1fae5', overflowX: 'auto', whiteSpace: 'pre-wrap' }}><code>{children}</code></pre>
                    ),
                    pre: ({ children }) => <>{children}</>,
                    strong: ({ children }) => (
                      <strong style={{ color: '#f3f4f6', fontWeight: 600 }}>{children}</strong>
                    ),
                    li: ({ children }) => (
                      <div style={{ margin: '4px 0', paddingLeft: '16px', color: '#d1d5db' }}>
                        <span style={{ color: '#60a5fa' }}>•</span> {children}
                      </div>
                    ),
                    hr: () => (
                      <hr style={{ border: 'none', borderTop: '1px solid #4b5563', margin: '16px 0' }} />
                    ),
                    p: ({ children }) => (
                      <p style={{ margin: '8px 0', color: '#d1d5db' }}>{children}</p>
                    )
                  }}
                >
                  {cleanAnalysisText(analysisData.analysis)}
                </ReactMarkdown>
              </div>
            </Box>
            
            <Box fontSize="body-s" color="text-status-inactive">
              Analysis generated at: {analysisData.timestamp ? new Date(analysisData.timestamp).toLocaleString() : 'Just now'}
            </Box>
            
          </SpaceBetween>
        </Container>

      </SpaceBetween>
    </Modal>
  );
}
