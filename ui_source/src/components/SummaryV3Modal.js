import React from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Modal,
  Box,
  SpaceBetween,
  Button,
  Header,
  Container
} from '@cloudscape-design/components';

const SummaryV3Modal = ({ visible, onDismiss, summaryData }) => {

  const getSummaryContent = () => {
    if (!summaryData) return 'No analysis data available';
    
    try {
      // axios parses JSON automatically → summaryData.summary
      // raw API Gateway response → summaryData.body (string)
      if (summaryData.summary) return summaryData.summary;
      if (summaryData.body) {
        const parsedBody = typeof summaryData.body === 'string' ? JSON.parse(summaryData.body) : summaryData.body;
        return parsedBody?.summary || 'No summary found';
      }
      return 'No analysis data available';
    } catch (error) {
      return `Error parsing data: ${error.message}`;
    }
  };

  const summaryContent = getSummaryContent();

  return (
    <Modal
      onDismiss={onDismiss}
      visible={visible}
      closeAriaLabel="Close modal"
      size="max"
      header={<Header variant="h1">🚀 MySQL Upgrade Analysis V3</Header>}
    >
      <SpaceBetween direction="vertical" size="l">
        <Container>
          <Box>
            <div 
              style={{ 
                lineHeight: '1.6',
                fontSize: '14px',
                color: '#232f3e',
                maxHeight: '70vh',
                overflowY: 'auto',
                padding: '10px'
              }}
            >
              <ReactMarkdown
                components={{
                  h2: ({ children }) => (
                    <h2 style={{ color: '#0073bb', margin: '20px 0 10px 0', fontSize: '18px', fontWeight: 'bold' }}>{children}</h2>
                  ),
                  h3: ({ children }) => (
                    <h3 style={{ color: '#0073bb', margin: '15px 0 8px 0', fontSize: '16px', fontWeight: 'bold' }}>{children}</h3>
                  ),
                  strong: ({ children }) => (
                    <strong style={{ color: '#0073bb' }}>{children}</strong>
                  ),
                  em: ({ children }) => (
                    <em>{children}</em>
                  ),
                  code: ({ inline, children }) => (
                    inline 
                      ? <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px', fontFamily: 'monospace', color: '#d63384' }}>{children}</code>
                      : <pre style={{ background: '#232f3e', color: '#ffffff', padding: '15px', borderRadius: '6px', overflowX: 'auto', margin: '10px 0', fontFamily: 'monospace', fontSize: '13px' }}><code>{children}</code></pre>
                  ),
                  pre: ({ children }) => <>{children}</>,
                  li: ({ children }) => (
                    <li style={{ margin: '5px 0' }}>{children}</li>
                  ),
                  p: ({ children }) => (
                    <p style={{ margin: '10px 0', lineHeight: '1.6' }}>{children}</p>
                  )
                }}
              >
                {summaryContent}
              </ReactMarkdown>
            </div>
          </Box>
        </Container>

        <Box float="right">
          <Button onClick={onDismiss} variant="primary">Close</Button>
        </Box>
      </SpaceBetween>
    </Modal>
  );
};

export default SummaryV3Modal;
