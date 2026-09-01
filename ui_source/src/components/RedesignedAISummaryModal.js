import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Modal,
  Box,
  SpaceBetween,
  Alert,
  Tabs,
  Container,
  Header,
  ColumnLayout,
  StatusIndicator,
  Badge,
  ProgressBar,
  Cards,
  Button,
  TextContent,
  ExpandableSection,
  Table,
  Link,
  Grid
} from '@cloudscape-design/components';

export default function RedesignedAISummaryModal({ 
  visible, 
  onDismiss, 
  summaryData, 
  selectedInstances 
}) {
  const [activeTabId, setActiveTabId] = useState('overview');

  // Helper functions for consistent styling
  const getRiskColor = (risk) => {
    switch(risk?.toLowerCase()) {
      case 'high': return 'red';
      case 'medium': return 'orange';
      case 'low': return 'green';
      default: return 'grey';
    }
  };

  const getSeverityType = (severity) => {
    switch(severity?.toLowerCase()) {
      case 'critical': return 'error';
      case 'high': return 'error';
      case 'medium': return 'warning';
      case 'low': return 'success';
      default: return 'info';
    }
  };

  const getPriorityColor = (priority) => {
    switch(priority?.toLowerCase()) {
      case 'critical': return 'red';
      case 'high': return 'red';
      case 'medium': return 'orange';
      case 'low': return 'green';
      default: return 'grey';
    }
  };

  const getComplexityColor = (complexity) => {
    switch(complexity?.toLowerCase()) {
      case 'simple': 
      case 'low': 
      case 'easy': return 'green';
      case 'moderate': 
      case 'medium': return 'orange';
      case 'complex': 
      case 'high': 
      case 'difficult': return 'red';
      default: return 'grey';
    }
  };

  // Extract data with consistent fallbacks
  const executiveSummary = summaryData?.executive_summary || {};
  const detailedFindings = summaryData?.detailed_findings || [];
  const recommendations = summaryData?.actionable_recommendations || [];
  const upgradePlan = summaryData?.upgrade_plan || {};
  const riskAssessment = summaryData?.risk_assessment || {};
  const instanceAnalysis = summaryData?.instance_specific_analysis || [];
  const analysisMetadata = summaryData?.analysis_metadata || {};

  // Calculate overall readiness score with fallback
  const calculateReadinessScore = () => {
    if (executiveSummary.readiness_score) return executiveSummary.readiness_score;
    if (instanceAnalysis.length > 0) {
      const avgScore = instanceAnalysis.reduce((sum, inst) => sum + (inst.readiness_score || 50), 0) / instanceAnalysis.length;
      return Math.round(avgScore);
    }
    return 50;
  };

  const readinessScore = calculateReadinessScore();

  // Overview Tab - Redesigned for consistency
  const overviewTab = (
    <SpaceBetween direction="vertical" size="l">
      {/* Executive Summary Card */}
      <Container header={<Header variant="h2">Executive Summary</Header>}>
        <Grid gridDefinition={[{ colspan: 4 }, { colspan: 4 }, { colspan: 4 }]}>
          <div>
            <Box variant="awsui-key-label">Overall Readiness</Box>
            <StatusIndicator 
              type={executiveSummary.overall_readiness === 'ready' ? 'success' : 
                    executiveSummary.overall_readiness === 'caution' ? 'warning' : 'error'}
            >
              {executiveSummary.overall_readiness?.toUpperCase() || 'UNKNOWN'}
            </StatusIndicator>
          </div>
          <div>
            <Box variant="awsui-key-label">Risk Level</Box>
            <Badge color={getRiskColor(executiveSummary.risk_level)}>
              {executiveSummary.risk_level?.toUpperCase() || 'UNKNOWN'}
            </Badge>
          </div>
          <div>
            <Box variant="awsui-key-label">Estimated Time</Box>
            <Box>{executiveSummary.estimated_upgrade_time || 'Not specified'}</Box>
          </div>
        </Grid>
      </Container>

      {/* Readiness Score Card */}
      <Container header={<Header variant="h3">Upgrade Readiness Score</Header>}>
        <SpaceBetween direction="vertical" size="s">
          <ProgressBar
            value={readinessScore}
            additionalInfo={`${readinessScore}/100`}
            description="Overall upgrade readiness based on comprehensive analysis"
            variant={readinessScore >= 80 ? 'success' : readinessScore >= 60 ? 'warning' : 'error'}
          />
          <Box variant="small" color={readinessScore >= 80 ? 'text-status-success' : 
                                     readinessScore >= 60 ? 'text-status-warning' : 'text-status-error'}>
            {readinessScore >= 80 && "✅ Ready for upgrade with minimal risk"}
            {readinessScore >= 60 && readinessScore < 80 && "⚠️ Proceed with caution - address warnings first"}
            {readinessScore < 60 && "❌ Not ready - critical issues must be resolved"}
          </Box>
        </SpaceBetween>
      </Container>

      {/* Key Metrics Cards */}
      <Container header={<Header variant="h3">Analysis Metrics</Header>}>
        <Grid gridDefinition={[{ colspan: 3 }, { colspan: 3 }, { colspan: 3 }, { colspan: 3 }]}>
          <div style={{ textAlign: 'center', padding: '16px', border: '1px solid #d5dbdb', borderRadius: '8px' }}>
            <Box variant="awsui-key-label">Critical Issues</Box>
            <div style={{ fontSize: '24px', fontWeight: 'bold', margin: '8px 0' }}>
              <Badge color={executiveSummary.critical_issues_count > 0 ? 'red' : 'green'} size="large">
                {executiveSummary.critical_issues_count || 0}
              </Badge>
            </div>
          </div>
          <div style={{ textAlign: 'center', padding: '16px', border: '1px solid #d5dbdb', borderRadius: '8px' }}>
            <Box variant="awsui-key-label">Recommendations</Box>
            <div style={{ fontSize: '24px', fontWeight: 'bold', margin: '8px 0' }}>
              <Badge color="blue" size="large">{recommendations.length || 0}</Badge>
            </div>
          </div>
          <div style={{ textAlign: 'center', padding: '16px', border: '1px solid #d5dbdb', borderRadius: '8px' }}>
            <Box variant="awsui-key-label">Instances Analyzed</Box>
            <div style={{ fontSize: '24px', fontWeight: 'bold', margin: '8px 0' }}>
              <Badge color="grey" size="large">{instanceAnalysis.length || selectedInstances?.length || 0}</Badge>
            </div>
          </div>
          <div style={{ textAlign: 'center', padding: '16px', border: '1px solid #d5dbdb', borderRadius: '8px' }}>
            <Box variant="awsui-key-label">Analysis Confidence</Box>
            <div style={{ fontSize: '24px', fontWeight: 'bold', margin: '8px 0' }}>
              <Badge color={analysisMetadata.analysis_confidence === 'high' ? 'green' : 
                           analysisMetadata.analysis_confidence === 'medium' ? 'orange' : 'red'} size="large">
                {analysisMetadata.analysis_confidence?.toUpperCase() || 'UNKNOWN'}
              </Badge>
            </div>
          </div>
        </Grid>
      </Container>

      {/* Analysis Summary */}
      {executiveSummary.summary_text && (
        <Container header={<Header variant="h3">AI Analysis Summary</Header>}>
          <TextContent>
            <ReactMarkdown>{executiveSummary.summary_text}</ReactMarkdown>
          </TextContent>
        </Container>
      )}

      {/* Analysis Metadata */}
      {analysisMetadata.analysis_timestamp && (
        <Container header={<Header variant="h3">Analysis Details</Header>}>
          <Grid gridDefinition={[{ colspan: 6 }, { colspan: 6 }]}>
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Analysis Time</Box>
                <Box>{new Date(analysisMetadata.analysis_timestamp).toLocaleString()}</Box>
              </div>
              <div>
                <Box variant="awsui-key-label">Processing Time</Box>
                <Box>{analysisMetadata.processing_time_seconds}s</Box>
              </div>
            </ColumnLayout>
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Reports Found</Box>
                <Box>{analysisMetadata.reports_found || 0}/{analysisMetadata.instances_processed || 0}</Box>
              </div>
              <div>
                <Box variant="awsui-key-label">Analysis Engine</Box>
                <Box>AWS Bedrock Claude 3</Box>
              </div>
            </ColumnLayout>
          </Grid>
        </Container>
      )}
    </SpaceBetween>
  );

  // Detailed Analysis Tab - Redesigned with proper expandable sections
  const detailedAnalysisTab = (
    <SpaceBetween direction="vertical" size="l">
      {/* Risk Assessment */}
      <Container header={<Header variant="h2">Risk Assessment</Header>}>
        <SpaceBetween direction="vertical" size="m">
          <Grid gridDefinition={[{ colspan: 6 }, { colspan: 6 }]}>
            <div>
              <Box variant="awsui-key-label">Overall Risk Level</Box>
              <div style={{ marginTop: '8px' }}>
                {riskAssessment.overall_risk ? (
                  <StatusIndicator type={getRiskColor(riskAssessment.overall_risk) === 'red' ? 'error' : 
                                        getRiskColor(riskAssessment.overall_risk) === 'orange' ? 'warning' : 'success'}>
                    <Box variant="strong">{riskAssessment.overall_risk.toUpperCase()}</Box>
                  </StatusIndicator>
                ) : (
                  <StatusIndicator type="info">
                    <Box variant="strong">NOT SPECIFIED</Box>
                  </StatusIndicator>
                )}
              </div>
            </div>
            <div>
              <Box variant="awsui-key-label">Upgrade Complexity</Box>
              <div style={{ marginTop: '8px' }}>
                {riskAssessment.upgrade_complexity ? (
                  <StatusIndicator type={getComplexityColor(riskAssessment.upgrade_complexity) === 'green' ? 'success' : 
                                        getComplexityColor(riskAssessment.upgrade_complexity) === 'orange' ? 'warning' : 'error'}>
                    <Box variant="strong">{riskAssessment.upgrade_complexity.toUpperCase()}</Box>
                  </StatusIndicator>
                ) : (
                  <StatusIndicator type="info">
                    <Box variant="strong">NOT SPECIFIED</Box>
                  </StatusIndicator>
                )}
              </div>
            </div>
          </Grid>
          
          {riskAssessment.risk_factors && riskAssessment.risk_factors.length > 0 && (
            <ExpandableSection headerText={`Risk Factors (${riskAssessment.risk_factors.length})`} defaultExpanded>
              <Table
                columnDefinitions={[
                  { 
                    id: 'factor', 
                    header: 'Risk Factor', 
                    cell: item => (
                      <Box>
                        <Box variant="strong">{item?.factor || 'Unknown factor'}</Box>
                      </Box>
                    ),
                    width: 250
                  },
                  { 
                    id: 'mitigation', 
                    header: 'Mitigation Strategy', 
                    cell: item => (
                      <Box>
                        <div style={{ 
                          maxWidth: '450px', 
                          wordWrap: 'break-word', 
                          whiteSpace: 'normal',
                          lineHeight: '1.4'
                        }}>
                          {item?.mitigation || 'No mitigation strategy specified'}
                        </div>
                      </Box>
                    )
                  },
                  { 
                    id: 'impact', 
                    header: 'Impact Level', 
                    cell: item => {
                      if (!item?.impact || item.impact.toString().trim() === '') {
                        return (
                          <StatusIndicator type="info">
                            <Box variant="strong">NOT SPECIFIED</Box>
                          </StatusIndicator>
                        );
                      }
                      
                      const impactColor = getRiskColor(item.impact);
                      const indicatorType = impactColor === 'red' ? 'error' : 
                                          impactColor === 'orange' ? 'warning' : 'success';
                      
                      return (
                        <StatusIndicator type={indicatorType}>
                          <Box variant="strong">{item.impact.toString().toUpperCase()}</Box>
                        </StatusIndicator>
                      );
                    },
                    width: 140
                  }
                ]}
                items={riskAssessment.risk_factors}
                variant="embedded"
                stripedRows
                wrapLines
              />
            </ExpandableSection>
          )}
        </SpaceBetween>
      </Container>

      {/* Detailed Findings */}
      <Container header={<Header variant="h2">Detailed Findings</Header>}>
        {detailedFindings && detailedFindings.length > 0 ? (
          <ExpandableSection headerText={`Analysis Findings (${detailedFindings.length})`} defaultExpanded>
            <Table
              columnDefinitions={[
                { 
                  id: 'title', 
                  header: 'Finding', 
                  cell: item => (
                    <Box>
                      <Box variant="strong">{item?.title || 'No title available'}</Box>
                    </Box>
                  ),
                  width: 250
                },
                { 
                  id: 'description', 
                  header: 'Description', 
                  cell: item => (
                    <Box>
                      <div style={{ 
                        maxWidth: '450px', 
                        wordWrap: 'break-word', 
                        whiteSpace: 'normal',
                        lineHeight: '1.4'
                      }}>
                        {item?.description || 'No description available'}
                      </div>
                    </Box>
                  )
                },
                { 
                  id: 'category', 
                  header: 'Category', 
                  cell: item => (
                    <Badge color="blue" size="large">{item?.category?.toUpperCase() || 'UNKNOWN'}</Badge>
                  ), 
                  width: 160
                },
                { 
                  id: 'severity', 
                  header: 'Severity', 
                  cell: item => (
                    <StatusIndicator type={getSeverityType(item?.severity)}>
                      <Box variant="strong">{item?.severity?.toUpperCase() || 'UNKNOWN'}</Box>
                    </StatusIndicator>
                  ),
                  width: 140
                }
              ]}
              items={detailedFindings}
              variant="embedded"
              stripedRows
              wrapLines
            />
          </ExpandableSection>
        ) : (
          <Box textAlign="center" color="text-status-inactive" padding="xl">
            <Box variant="strong">No detailed findings available</Box>
            <Box variant="p">Run precheck reports for comprehensive analysis</Box>
          </Box>
        )}
      </Container>

      {/* Instance-Specific Analysis */}
      <Container header={<Header variant="h2">Instance Analysis</Header>}>
        {instanceAnalysis && instanceAnalysis.length > 0 ? (
          <Cards
            cardDefinition={{
              header: item => (
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <span style={{ fontWeight: 'bold', fontSize: '16px' }}>
                    {item?.database_name || 'Unknown Database'}
                  </span>
                </div>
              ),
              sections: [
                {
                  id: 'readiness',
                  header: 'Readiness Score',
                  content: item => (
                    <ProgressBar
                      value={item?.readiness_score || 50}
                      additionalInfo={`${item?.readiness_score || 50}/100`}
                      variant={item?.readiness_score >= 80 ? 'success' : 
                              item?.readiness_score >= 60 ? 'warning' : 'error'}
                    />
                  )
                },
                {
                  id: 'issues',
                  header: 'Specific Issues',
                  content: item => (
                    item?.specific_issues && item.specific_issues.length > 0 ? (
                      <SpaceBetween direction="vertical" size="xs">
                        {item.specific_issues.slice(0, 3).map((issue, index) => (
                          <div key={index} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <StatusIndicator type={getSeverityType(issue?.severity)}>
                              {issue?.issue || 'Unknown issue'}
                            </StatusIndicator>
                          </div>
                        ))}
                        {item.specific_issues.length > 3 && (
                          <Box variant="small" color="text-status-inactive">
                            +{item.specific_issues.length - 3} more issues
                          </Box>
                        )}
                      </SpaceBetween>
                    ) : (
                      <Box color="text-status-success">✅ No critical issues found</Box>
                    )
                  )
                }
              ]
            }}
            items={instanceAnalysis}
            cardsPerRow={[{ cards: 1 }, { minWidth: 500, cards: 2 }]}
          />
        ) : (
          <Box textAlign="center" color="text-status-inactive" padding="xl">
            <Box variant="strong">No instance-specific analysis available</Box>
            <Box variant="p">Analysis will appear here after processing HTML reports</Box>
          </Box>
        )}
      </Container>
    </SpaceBetween>
  );

  // Action Plan Tab - Redesigned with better organization
  const actionPlanTab = (
    <SpaceBetween direction="vertical" size="l">
      {/* Actionable Recommendations */}
      <Container header={<Header variant="h2">Actionable Recommendations</Header>}>
        {recommendations && recommendations.length > 0 ? (
          <ExpandableSection headerText={`Recommendations (${recommendations.length})`} defaultExpanded>
            <Table
              columnDefinitions={[
                { 
                  id: 'title', 
                  header: 'Recommendation', 
                  cell: item => (
                    <Box>
                      <Box variant="strong">{item?.title || 'No title available'}</Box>
                    </Box>
                  ),
                  width: 250
                },
                { 
                  id: 'category', 
                  header: 'Category', 
                  cell: item => (
                    <Badge color="blue">
                      {item?.category?.replace('_', ' ').toUpperCase() || 'UNKNOWN'}
                    </Badge>
                  ), 
                  width: 160
                },
                { 
                  id: 'effort', 
                  header: 'Estimated Effort', 
                  cell: item => (
                    <Badge color="grey">{item?.estimated_effort || 'Not specified'}</Badge>
                  ), 
                  width: 140 
                },
                { 
                  id: 'priority', 
                  header: 'Priority', 
                  cell: item => (
                    <StatusIndicator type={getSeverityType(item?.priority)}>
                      <Box variant="strong">{item?.priority?.toUpperCase() || 'UNKNOWN'}</Box>
                    </StatusIndicator>
                  ),
                  width: 140
                },
                { 
                  id: 'automation', 
                  header: 'Automation', 
                  cell: item => (
                    <Badge color={item?.automation_possible ? 'green' : 'orange'}>
                      {item?.automation_possible ? 'POSSIBLE' : 'MANUAL'}
                    </Badge>
                  ), 
                  width: 140
                }
              ]}
              items={recommendations}
              variant="embedded"
              stripedRows
              wrapLines
            />
          </ExpandableSection>
        ) : (
          <Box textAlign="center" color="text-status-inactive" padding="xl">
            <Box variant="strong">No recommendations available</Box>
            <Box variant="p">Generate precheck reports for detailed recommendations</Box>
          </Box>
        )}
      </Container>

      {/* Upgrade Plan */}
      {(upgradePlan.pre_upgrade_tasks || upgradePlan.upgrade_sequence || upgradePlan.post_upgrade_validation) && (
        <Container header={<Header variant="h2">Upgrade Plan</Header>}>
          <SpaceBetween direction="vertical" size="m">
            {upgradePlan.pre_upgrade_tasks && upgradePlan.pre_upgrade_tasks.length > 0 && (
              <ExpandableSection headerText={`Pre-Upgrade Tasks (${upgradePlan.pre_upgrade_tasks.length})`} defaultExpanded>
                <Table
                  columnDefinitions={[
                    { 
                      id: 'task', 
                      header: 'Task', 
                      cell: item => (
                        <Box>
                          <div style={{ 
                            maxWidth: '400px', 
                            wordWrap: 'break-word', 
                            whiteSpace: 'normal',
                            lineHeight: '1.4'
                          }}>
                            <Box variant="strong">{item?.task || 'No task specified'}</Box>
                          </div>
                        </Box>
                      ),
                      width: 400
                    },
                    { 
                      id: 'time', 
                      header: 'Estimated Time', 
                      cell: item => (
                        <Badge color="grey">{item?.estimated_time || 'Not specified'}</Badge>
                      ),
                      width: 200
                    },
                    { 
                      id: 'priority', 
                      header: 'Priority', 
                      cell: item => (
                        <Badge color={getPriorityColor(item?.priority)} size="large">
                          {item?.priority?.toUpperCase() || 'UNKNOWN'}
                        </Badge>
                      ),
                      width: 200
                    }
                  ]}
                  items={upgradePlan.pre_upgrade_tasks}
                  variant="embedded"
                  stripedRows
                  wrapLines
                />
              </ExpandableSection>
            )}

            {upgradePlan.upgrade_sequence && upgradePlan.upgrade_sequence.length > 0 && (
              <ExpandableSection headerText={`Upgrade Sequence (${upgradePlan.upgrade_sequence.length} steps)`}>
                <Table
                  columnDefinitions={[
                    { 
                      id: 'step', 
                      header: 'Step', 
                      cell: item => (
                        <Box>
                          <div style={{ 
                            maxWidth: '400px', 
                            wordWrap: 'break-word', 
                            whiteSpace: 'normal',
                            lineHeight: '1.4'
                          }}>
                            <Box variant="strong">{item?.step || 'No step specified'}</Box>
                          </div>
                        </Box>
                      ),
                      width: 400
                    },
                    { 
                      id: 'considerations', 
                      header: 'Important Considerations', 
                      cell: item => (
                        <Box>
                          <div style={{ 
                            maxWidth: '400px', 
                            wordWrap: 'break-word', 
                            whiteSpace: 'normal',
                            lineHeight: '1.4'
                          }}>
                            {item?.considerations || 'No considerations specified'}
                          </div>
                        </Box>
                      ),
                      width: 400
                    }
                  ]}
                  items={upgradePlan.upgrade_sequence}
                  variant="embedded"
                  stripedRows
                  wrapLines
                />
              </ExpandableSection>
            )}

            {upgradePlan.post_upgrade_validation && upgradePlan.post_upgrade_validation.length > 0 && (
              <ExpandableSection headerText={`Post-Upgrade Validation (${upgradePlan.post_upgrade_validation.length} checks)`}>
                <Table
                  columnDefinitions={[
                    { 
                      id: 'check', 
                      header: 'Validation Check', 
                      cell: item => (
                        <Box>
                          <div style={{ 
                            maxWidth: '400px', 
                            wordWrap: 'break-word', 
                            whiteSpace: 'normal',
                            lineHeight: '1.4'
                          }}>
                            <Box variant="strong">{item?.check || 'No check specified'}</Box>
                          </div>
                        </Box>
                      ),
                      width: 400
                    },
                    { 
                      id: 'expected', 
                      header: 'Expected Result', 
                      cell: item => (
                        <Box>
                          <div style={{ 
                            maxWidth: '400px', 
                            wordWrap: 'break-word', 
                            whiteSpace: 'normal',
                            lineHeight: '1.4'
                          }}>
                            {item?.expected_result || 'No expected result specified'}
                          </div>
                        </Box>
                      ),
                      width: 400
                    }
                  ]}
                  items={upgradePlan.post_upgrade_validation}
                  variant="embedded"
                  stripedRows
                  wrapLines
                />
              </ExpandableSection>
            )}

            {upgradePlan.rollback_plan && upgradePlan.rollback_plan.length > 0 && (
              <ExpandableSection headerText={`Rollback Plan (${upgradePlan.rollback_plan.length} steps)`}>
                <Table
                  columnDefinitions={[
                    { 
                      id: 'step', 
                      header: 'Rollback Step', 
                      cell: item => (
                        <Box>
                          <div style={{ 
                            maxWidth: '400px', 
                            wordWrap: 'break-word', 
                            whiteSpace: 'normal',
                            lineHeight: '1.4'
                          }}>
                            <Box variant="strong">{item?.step || 'No step specified'}</Box>
                          </div>
                        </Box>
                      ),
                      width: 400
                    },
                    { 
                      id: 'condition', 
                      header: 'Trigger Condition', 
                      cell: item => (
                        <Box>
                          <div style={{ 
                            maxWidth: '400px', 
                            wordWrap: 'break-word', 
                            whiteSpace: 'normal',
                            lineHeight: '1.4'
                          }}>
                            {item?.condition || 'No condition specified'}
                          </div>
                        </Box>
                      ),
                      width: 400
                    }
                  ]}
                  items={upgradePlan.rollback_plan}
                  variant="embedded"
                  stripedRows
                  wrapLines
                />
              </ExpandableSection>
            )}
          </SpaceBetween>
        </Container>
      )}
    </SpaceBetween>
  );

  const tabs = [
    {
      label: "Overview",
      id: "overview",
      content: overviewTab
    },
    {
      label: "Detailed Analysis",
      id: "analysis",
      content: detailedAnalysisTab
    },
    {
      label: "Action Plan",
      id: "actions",
      content: actionPlanTab
    }
  ];

  return (
    <Modal
      onDismiss={onDismiss}
      visible={visible}
      size="max"
      header="MySQL Upgrade AI Analysis Summary"
    >
      <SpaceBetween direction="vertical" size="l">
        {/* Analysis confidence alert */}
        {analysisMetadata.analysis_confidence === 'low' && (
          <Alert type="warning" header="Limited Analysis Data">
            This analysis is based on limited data. For comprehensive insights, ensure all instances have 
            generated HTML precheck reports before running the AI summary.
          </Alert>
        )}

        {/* Main content tabs */}
        <Tabs
          tabs={tabs}
          activeTabId={activeTabId}
          onChange={({ detail }) => setActiveTabId(detail.activeTabId)}
        />
      </SpaceBetween>
    </Modal>
  );
}
