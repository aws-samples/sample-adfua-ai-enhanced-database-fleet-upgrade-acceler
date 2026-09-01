import React, { useState, useEffect } from 'react';
import Papa from 'papaparse';
import axios from 'axios';
import { generateAISummaryDirect, testLambdaConnection } from './services/awsLambdaService';
import { getApiBase, getAccountId } from './config';
import { isAuthConfigured, getSession, signOut, getCurrentUsername } from './services/auth';
import {
  AppLayout,
  ContentLayout,
  Header,
  Container,
  SpaceBetween,
  Button,
  Table,
  Box,
  TextContent,
  Alert,
  FormField,
  Input,
  FileUpload,
  Badge,
  StatusIndicator,
  ProgressBar,
  Modal,
  Cards,
  ColumnLayout
} from '@cloudscape-design/components';
import { TopNavigation, SideNavigation, HelpPanel, CredentialsModal, ConnectionSetup, Login } from './components';
import RedesignedAISummaryModal from './components/RedesignedAISummaryModal';
import PrecheckResultsModal from './components/PrecheckResultsModal';
import SummaryV2Modal from './components/SummaryV2Modal';
import SummaryV3Modal from './components/SummaryV3Modal';
import ECSLogViewer from './components/ECSLogViewer';
import ErrorAnalysisModal from './components/ErrorAnalysisModal';
import './App.css';

function App() {
  // ── Authentication gate (Finding #1) ─────────────────────────────────────
  const authRequired = isAuthConfigured();
  const [authChecked, setAuthChecked] = useState(!authRequired);
  const [authenticated, setAuthenticated] = useState(!authRequired);
  const [currentUser, setCurrentUser] = useState('');

  useEffect(() => {
    if (!authRequired) return;
    let mounted = true;
    (async () => {
      const session = await getSession();
      if (!mounted) return;
      if (session) {
        setAuthenticated(true);
        setCurrentUser((await getCurrentUsername()) || '');
      }
      setAuthChecked(true);
    })();
    return () => { mounted = false; };
  }, [authRequired]);

  const handleSignedIn = async () => {
    setAuthenticated(true);
    setCurrentUser((await getCurrentUsername()) || '');
  };

  const handleSignOut = () => {
    signOut();
    setAuthenticated(false);
    setCurrentUser('');
  };

  const [file, setFile] = useState([]);
  const [instances, setInstances] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);
  // API base loaded at runtime from /config.json (injected by CDK deploy)
  const API_BASE = getApiBase();
  const PRECHECK_API_ENDPOINT = `${API_BASE}/pre-checker`;
  const SUMMARY_API_ENDPOINT = `${API_BASE}/genai-summary`;
  const SUMMARY_V2_API_ENDPOINT = `${API_BASE}/genai-summary`;
  const SUMMARY_V3_API_ENDPOINT = `${API_BASE}/genai-summary`;
  const UPGRADE_API_ENDPOINT = `${API_BASE}/bg-deployment`;
  const SWITCHOVER_API_ENDPOINT = `${API_BASE}/switchover`;
  
  const [loading, setLoading] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [showCredentialsModal, setShowCredentialsModal] = useState(false);
  const [currentAction, setCurrentAction] = useState(''); // 'precheck', 'upgrade', or 'summary'
  const [precheckLoading, setPrecheckLoading] = useState(false);
  const [upgradeLoading, setUpgradeLoading] = useState(false);
  const [switchoverLoading, setSwitchoverLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryData, setSummaryData] = useState(null);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [enhancedSummaryData, setEnhancedSummaryData] = useState(null);
  // New V2 summary states
  const [summaryV2Loading, setSummaryV2Loading] = useState(false);
  const [summaryV2Data, setSummaryV2Data] = useState(null);
  const [showSummaryV2Modal, setShowSummaryV2Modal] = useState(false);
  // New V3 summary states
  const [summaryV3Loading, setSummaryV3Loading] = useState(false);
  const [summaryV3Data, setSummaryV3Data] = useState(null);
  const [showSummaryV3Modal, setShowSummaryV3Modal] = useState(false);
  const [v3ProcessingTime, setV3ProcessingTime] = useState(0);
  const [showPrecheckResultsModal, setShowPrecheckResultsModal] = useState(false);
  const [precheckResponse, setPrecheckResponse] = useState(null);
  
  // ECS Log Viewer states
  const [showLogViewer, setShowLogViewer] = useState(false);
  const [currentTaskArn, setCurrentTaskArn] = useState('');
  const [currentClusterName, setCurrentClusterName] = useState('');
  
  // Error Analysis states
  const [showErrorAnalysis, setShowErrorAnalysis] = useState(false);
  const [errorAnalysisData, setErrorAnalysisData] = useState(null);
  
  // Navigation state
  const [activeHref, setActiveHref] = useState('#/upload');
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);

  // Navigation handler
  const handleNavigationChange = ({ detail }) => {
    const { href } = detail;
    setActiveHref(href);
    // Handle navigation logic here
  };

  // Enhanced Summary handler - sends request to Lambda for HTML report analysis
  // Enhanced Summary handler - uses direct AWS SDK Lambda invocation (bypasses API Gateway timeout)
  const handleSummaryClick = async () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one instance to generate summary');
      return;
    }

    setSummaryLoading(true);
    setError('');
    setSuccess('');

    try {
      // Get selected instances data
      const selectedInstancesData = instances.filter(instance => 
        selectedItems.some(selected => selected.id === instance.id)
      );

      if (!selectedInstancesData || selectedInstancesData.length === 0) {
        setError('No instance data found for selected items. Please ensure instances are properly loaded.');
        return;
      }

      // Use direct Lambda invocation instead of API Gateway
      const result = await generateAISummaryDirect(selectedInstancesData);

      if (result.success) {
        // Set the summary data for the modal
        setSummaryData(result.data);
        setShowSummaryModal(true);
        setSuccess(`AI Summary generated successfully in ${result.duration} seconds using AWS Bedrock Claude 3 (Direct Lambda invocation)!`);
      } else {
        // Handle different types of errors
        let errorMessage = result.error;
        
        if (result.errorType === 'Timeout') {
          errorMessage = `⏱️ AI Analysis Timeout: The comprehensive AI analysis with AWS Bedrock Claude 3 took longer than expected (${result.duration}s).

This can happen when:
- HTML reports are very large or complex
- Bedrock service is experiencing high load
- Network connectivity issues

💡 Solutions:
1. Try again in a few minutes
2. Try with fewer database instances
3. Check if HTML reports exist: ${selectedInstancesData.map(i => `${i.database_name}-precheck-report.html`).join(', ')}

The direct Lambda invocation allows up to 5 minutes processing time, much longer than API Gateway's 29-second limit.`;
        } else if (result.errorType === 'AccessDenied') {
          errorMessage = `🔐 Access Denied: Unable to invoke Lambda function directly.

This could be due to:
- AWS credentials not configured properly
- Insufficient permissions for Lambda invocation
- Lambda function not accessible

💡 Solutions:
1. Check AWS credentials configuration
2. Verify Lambda function permissions
3. Try using the API Gateway endpoint as fallback`;
        } else if (result.errorType === 'FunctionNotFound') {
          errorMessage = `🔍 Lambda Function Not Found: The function 'mysql-upgrader-genai-summary' could not be found.

💡 Solutions:
1. Verify the Lambda function exists in us-east-1 region
2. Check the function name is correct
3. Ensure the function is deployed properly`;
        }
        
        setError(errorMessage);
      }

    } catch (err) {
      console.error('💥 Unexpected error in handleSummaryClick:', err);
      setError(`Unexpected error during AI Summary generation: ${err.message}. Please check the console for more details.`);
    } finally {
      setSummaryLoading(false);
    }
  };

  const handleSummaryV2Click = async () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one instance to generate AI summary');
      return;
    }

    setSummaryV2Loading(true);
    setError('');
    setSuccess('');

    try {
      const selectedInstancesData = instances.filter(instance =>
        selectedItems.some(selected => selected.id === instance.id)
      );

      if (!selectedInstancesData || selectedInstancesData.length === 0) {
        setError('No instance data found for selected items.');
        return;
      }

      const result = await generateAISummaryDirect(selectedInstancesData);

      if (result.success) {
        let body = result.data;
        if (typeof body === 'string') body = JSON.parse(body);
        if (body?.body) body = typeof body.body === 'string' ? JSON.parse(body.body) : body.body;

        // Check if BG deployment already exists
        if (body?.status === 'already_exists') {
          const warnings = body.bg_warnings || [];
          setPrecheckResponse({
            results: warnings.map(w => ({
              database_name: w.database_name,
              status: 'already_exists',
              message: w.message,
              deployment_id: w.deployment_id,
              bg_status: w.bg_status,
            }))
          });
          setShowPrecheckResultsModal(true);
          return;
        }

        setSummaryV2Data(body);
        setShowSummaryV2Modal(true);
        setSuccess(`AI Summary generated successfully in ${result.duration} seconds!`);
      } else {
        setError(`AI Summary failed: ${result.error}`);
      }

    } catch (err) {
      setError(`Unexpected error: ${err.message}`);
    } finally {
      setSummaryV2Loading(false);
    }
  };

  // V3 Summary handler with async processing
  const handleSummaryV3Click = async () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one instance for V3 AI summary');
      return;
    }

    setSummaryV3Loading(true);
    setError('');
    setSuccess('');
    setV3ProcessingTime(0);

    const startTime = Date.now();
    const timer = setInterval(() => {
      setV3ProcessingTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      const selectedInstancesData = instances.filter(instance => 
        selectedItems.some(selected => selected.id === instance.id)
      );

      const payload = {
        instances: selectedInstancesData,
        action: 'summary',
        async: true // Request async processing
      };

      // Step 1: Start async job (should return immediately with job ID)
      const startResponse = await axios.post(SUMMARY_V3_API_ENDPOINT, payload, {
        headers: { 'Content-Type': 'application/json' },
        timeout: 180000 // 3 minutes timeout to match API Gateway
      });

      const jobId = startResponse.data?.jobId || startResponse.data?.body?.jobId;
      if (!jobId) {
        // Fallback to sync processing if async not supported
        const syncPayload = { ...payload, async: false };
        const syncResponse = await axios.post(SUMMARY_V3_API_ENDPOINT, syncPayload, {
          headers: { 'Content-Type': 'application/json' },
          timeout: 180000 // 3 minutes timeout to match API Gateway
        });
        
        setSummaryV3Data(syncResponse.data);
        setShowSummaryV3Modal(true);
        setSuccess(`✅ V3 Summary completed (sync fallback) in ${Math.floor((Date.now() - startTime) / 1000)}s`);
        return;
      }

      // Step 2: Poll for completion
      let attempts = 0;
      const maxAttempts = 60; // 5 minutes max (60 * 5 seconds)
      
      while (attempts < maxAttempts) {
        attempts++;
        await new Promise(resolve => setTimeout(resolve, 5000)); // Wait 5 seconds
        
        try {
          const statusResponse = await axios.get(`${SUMMARY_V3_API_ENDPOINT}/status/${jobId}`, {
            timeout: 10000
          });

          const status = statusResponse.data?.status || statusResponse.data?.body?.status;
          const result = statusResponse.data?.result || statusResponse.data?.body?.result;

          if (status === 'COMPLETED' && result) {
            setSummaryV3Data(result);
            setShowSummaryV3Modal(true);
            setSuccess(`🚀 V3 Summary completed via async processing in ${Math.floor((Date.now() - startTime) / 1000)}s`);
            return;
          } else if (status === 'FAILED') {
            throw new Error(`Job failed: ${statusResponse.data?.error || 'Unknown error'}`);
          }
          
        } catch (pollError) {
          if (pollError.response?.status === 404 && attempts < 5) {
            continue;
          }
          throw pollError;
        }
      }

      throw new Error('Job timed out after 5 minutes');

    } catch (err) {
      console.error('❌ V3 Error:', err);
      
      let errorMessage = 'V3 Analysis failed: ';
      
      if (err.response?.status === 504) {
        errorMessage = `⏱️ Gateway timeout after ${Math.floor((Date.now() - startTime) / 1000)}s. 

🔧 **Recommended Solutions:**

**Option 1: Backend Async Processing**
• Modify your V3 Lambda to support async jobs
• Return job ID immediately, process in background
• Provide status endpoint for polling

**Option 2: Optimize V3 Lambda**  
• Reduce AI model complexity
• Implement caching for repeated analyses
• Use faster instance types (more memory/CPU)

**Option 3: Use AI Summary Instead**
• AI Summary completes in ~20 seconds
• Similar analysis capabilities
• Proven to work within timeout limits`;
      } else if (err.message.includes('timed out')) {
        errorMessage = `⏱️ ${err.message}. Consider optimizing the V3 Lambda or using the AI Summary endpoint.`;
      } else {
        errorMessage += err.message;
      }
      
      setError(errorMessage);
    } finally {
      clearInterval(timer);
      setSummaryV3Loading(false);
      setV3ProcessingTime(0);
    }
  };

  // Function to enhance response data - only used as fallback when Lambda doesn't provide complete analysis
  const enhanceResponseData = (apiResponse, selectedInstancesData) => {
    // If Lambda provided complete analysis, return as-is
    if (apiResponse.executive_summary && apiResponse.key_findings && apiResponse.recommendations) {
      return apiResponse;
    }

    const enhanced = { ...apiResponse };

    // Only enhance missing fields
    if (!enhanced.executive_summary || enhanced.executive_summary.length < 100) {
      enhanced.executive_summary = generateFallbackExecutiveSummary(selectedInstancesData);
    }

    if (!enhanced.recommendations || enhanced.recommendations.length === 0) {
      enhanced.recommendations = generateFallbackRecommendations(selectedInstancesData);
    }

    if (!enhanced.key_findings || enhanced.key_findings.length === 0) {
      enhanced.key_findings = generateFallbackFindings(selectedInstancesData);
    }

    if (!enhanced.risk_assessment) {
      enhanced.risk_assessment = generateFallbackRiskAssessment(selectedInstancesData);
    }

    return enhanced;
  };

  const generateFallbackExecutiveSummary = (instances) => {
    return `
      <p><strong>Fallback Analysis - HTML Reports Not Available</strong></p>
      <p>This analysis is based on configuration data only. For detailed insights, please ensure precheck reports have been generated first.</p>
      <p>Selected ${instances.length} database instance(s) for analysis. To get comprehensive AI insights, run the precheck process first to generate HTML reports.</p>
    `;
  };

  const generateFallbackRecommendations = (instances) => {
    return [
      {
        id: 'run-precheck-first',
        title: 'Generate Precheck Reports First',
        description: 'Run the precheck process to generate detailed HTML reports that can be analyzed by AI for comprehensive insights.',
        priority: 'High',
        category: 'Prerequisites',
        impact: 'Critical',
        effort: 'Low',
        automated: false,
        steps: [
          'Select the same database instances',
          'Click "Generate Precheck Report"',
          'Enter database credentials',
          'Wait for precheck completion',
          'Then run AI Summary again'
        ],
        benefits: [
          'Detailed compatibility analysis',
          'Specific error and warning identification',
          'Tailored recommendations based on actual database state',
          'Risk assessment based on real data'
        ],
        risks: []
      }
    ];
  };

  const generateFallbackFindings = (instances) => {
    return [
      {
        id: 'no-html-reports',
        title: 'No HTML Precheck Reports Found',
        description: 'AI analysis requires HTML precheck reports to provide detailed insights. Current analysis is limited to configuration data only.',
        severity: 'high',
        category: 'Prerequisites',
        affected_instances: instances.map(inst => inst.database_name),
        resolution: 'Run the precheck process first to generate HTML reports, then re-run the AI summary for comprehensive analysis.'
      }
    ];
  };

  const generateFallbackRiskAssessment = (instances) => {
    return {
      overall_risk: 'unknown',
      description: 'Risk assessment requires HTML precheck reports for accurate analysis. Please run precheck first to get detailed risk evaluation.',
      mitigation_strategies: [
        'Generate precheck reports for all selected instances',
        'Review HTML reports manually if AI analysis is not available',
        'Ensure proper backup procedures are in place',
        'Test upgrade process in staging environment first'
      ]
    };
  };

  // Config Generator handler
  const handleTestConnectionClick = () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one instance to configure');
      return;
    }
    setCurrentAction('test');
    setShowCredentialsModal(true);
  };

  // Precheck handler
  const handlePrecheckClick = () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one instance for precheck');
      return;
    }
    setCurrentAction('precheck');
    setShowCredentialsModal(true);
  };

  // Error log analysis with Bedrock
  const analyzeErrorLogs = async (taskArn, clusterName) => {
    try {
      const response = await axios.post(`${API_BASE}/analyze-logs`, {
        taskArn: taskArn,
        clusterName: clusterName,
        action: 'analyze_errors'
      });
      
      // Parse nested JSON if needed
      let analysisData = response.data;
      if (typeof analysisData.body === 'string') {
        analysisData = JSON.parse(analysisData.body);
      }
      
      return analysisData;
    } catch (error) {
      console.error('❌ Error analyzing logs:', error);
      return null;
    }
  };

  // Switchover handler
  const handleSwitchoverClick = () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one instance to switchover');
      return;
    }
    setCurrentAction('switchover');
    setShowCredentialsModal(true);
  };

  // Upgrade handler
  const handleUpgradeClick = () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one instance to upgrade');
      return;
    }
    setCurrentAction('upgrade');
    setShowCredentialsModal(true);
  };

  // Credentials confirmation handler
  const handleCredentialsConfirm = async (credentials) => {
    const isPrecheck   = currentAction === 'precheck';
    const isTest       = currentAction === 'test';
    const isSwitchover = currentAction === 'switchover';
    const setLoadingState = isPrecheck   ? setPrecheckLoading
                          : isTest       ? setTestLoading
                          : isSwitchover ? setSwitchoverLoading
                          : setUpgradeLoading;
    
    setLoadingState(true);
    setError('');
    setSuccess('');

    try {
      const selectedInstancesData = instances.filter(instance => 
        selectedItems.some(selected => selected.id === instance.id)
      );

      // ── Switchover ───────────────────────────────────────────────────
      if (isSwitchover) {
        setShowCredentialsModal(false);
        const response = await axios.post(SWITCHOVER_API_ENDPOINT, {
          instances: selectedInstancesData,
          username: credentials.username,
          password: credentials.password,
        }, { headers: { 'Content-Type': 'application/json' }, timeout: 60000 });

        let body = response.data?.body
          ? (typeof response.data.body === 'string' ? JSON.parse(response.data.body) : response.data.body)
          : response.data;

        const results = body.results || [];
        const ok   = results.filter(r => r.status === 'switchover_initiated');
        const fail = results.filter(r => r.status === 'error');

        if (fail.length === 0) {
          const taskArn     = ok[0]?.task_arn;
          const clusterName = ok[0]?.cluster_name || 'mysql-upgrade-cluster';
          if (taskArn) {
            setCurrentTaskArn(taskArn);
            setCurrentClusterName(clusterName);
            setShowLogViewer(true);
          }
          setSuccess(
            `✅ Switchover initiated for ${ok.length} instance(s). ` +
            ok.map(r => `${r.database_name}: deployment ${r.deployment_id}`).join(' | ')
          );
        } else {
          setError(
            `❌ ${fail.length} error(s): ` +
            fail.map(r => `${r.database_name}: ${r.error}`).join(' | ')
          );
        }
        return;
      }

      // ── Test Connection ──────────────────────────────────────────────
      if (isTest) {
        setShowCredentialsModal(false);
        const response = await axios.post(`${API_BASE}/test-connection`, {
          instances: selectedInstancesData,
          username: credentials.username,
          password: credentials.password,
        }, { headers: { 'Content-Type': 'application/json' }, timeout: 30000 });

        let body = response.data?.body
          ? (typeof response.data.body === 'string' ? JSON.parse(response.data.body) : response.data.body)
          : response.data;

        const results = body.results || [];
        const ok   = results.filter(r => r.status === 'configured');
        const fail = results.filter(r => r.status === 'error');

        if (fail.length === 0) {
          setSuccess(
            `✅ ${ok.length} instance(s) configured. Credentials saved. Ready for precheck. ` +
            ok.map(r => `${r.database_name}: ${r.host}:${r.port} · Secret ${r.secret_action}`).join(' | ')
          );
        } else {
          setError(
            `❌ ${fail.length} error(s): ` +
            fail.map(r => `${r.database_name}: ${r.error}`).join(' | ')
          );
        }
        return;
      }

      const payload = {
        instances: selectedInstancesData,
        selectedItems: selectedInstancesData,
        action: currentAction,
        credentials: {
          username: credentials.username,
          password: credentials.password
        }
      };

      // Use correct endpoint based on action
      const endpoint = currentAction === 'precheck' ? PRECHECK_API_ENDPOINT : UPGRADE_API_ENDPOINT;  // switchover handled above
      
      const response = await axios.post(endpoint, payload, {
        headers: { 'Content-Type': 'application/json' }
      });

      if (isPrecheck) {
        let responseBody = response.data;
        if (responseBody?.body) {
          responseBody = typeof responseBody.body === 'string'
            ? JSON.parse(responseBody.body)
            : responseBody.body;
        }
        // Update precheck response with real data and show modal
        setPrecheckResponse(responseBody);
        setShowPrecheckResultsModal(true);
        // Open log viewer only if a task was actually started
        const startedResult = (responseBody?.results || []).find(r => r.status === 'started');
        if (startedResult?.task_arn) {
          setCurrentTaskArn(startedResult.task_arn);
          setCurrentClusterName(startedResult.cluster_name || 'mysql-upgrade-cluster');
          setShowLogViewer(true);
        }
      } else {
        // For upgrade (BG deployment), extract task info and show logs
        let responseBody = response.data;
        if (responseBody?.body) {
          responseBody = typeof responseBody.body === 'string'
            ? JSON.parse(responseBody.body)
            : responseBody.body;
        }

        const results = responseBody?.results || [];
        const alreadyExists = results.filter(r => r.status === 'already_exists');
        const started = results.filter(r => r.status === 'started');

        if (alreadyExists.length > 0 && started.length === 0) {
          // All instances already have BG deployments — show modal
          setPrecheckResponse(responseBody);
          setShowPrecheckResultsModal(true);
        } else {
          if (alreadyExists.length > 0) {
            // Mixed — some started, some already exist — show modal + logs
            setPrecheckResponse(responseBody);
            setShowPrecheckResultsModal(true);
          } else {
            setSuccess(`✅ Upgrade initiated for ${started.length} instance(s).`);
          }

          const startedResult = started[0];
          if (startedResult?.task_arn) {
            setCurrentTaskArn(startedResult.task_arn);
            setCurrentClusterName(startedResult.cluster_name || 'mysql-upgrade-cluster');
            setShowLogViewer(true);
          }
        }
      }
      
      setShowCredentialsModal(false);
    } catch (err) {
      if (isTest) {
        setError('Test connection failed: ' + (err.response?.data?.message || err.message));
      } else if (isSwitchover) {
        setError('Switchover failed: ' + (err.response?.data?.message || err.message));
      } else if (isPrecheck) {
        // precheck errors shown via results modal, not here
      } else {
        setError('Failed to send upgrade request: ' + (err.response?.data?.message || err.message));
      }
    } finally {
      setLoadingState(false);
    }
  };

  const handleFileUpload = (detail) => {
    const uploadedFiles = detail.value;
    setFile(uploadedFiles);
    
    if (uploadedFiles.length === 0) {
      setInstances([]);
      setSelectedItems([]);
      return;
    }

    setUploadLoading(true);
    setError('');
    setSuccess('');

    const uploadedFile = uploadedFiles[0];

    // Parse CSV file
    Papa.parse(uploadedFile, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.errors.length > 0) {
          setError('Error parsing CSV file: ' + results.errors[0].message);
          setUploadLoading(false);
          return;
        }

        const parsedInstances = results.data.map((row, index) => ({
          id: index.toString(),
          database_name: row.database_name || '',
          cluster_type: row.cluster_type || '',
          region: row.region || '',
          rds_instance: row.rds_instance || '',
          aurora_cluster: row.aurora_cluster || '',
          target_parameter_family: row.target_parameter_family || '',
          target_engine_version: row.target_engine_version || '',
          bucket_name: `adua-mysql-upgrade-${getAccountId() || '<your-aws-account-id>'}`
        }));

        setInstances(parsedInstances);
        setSelectedItems([]);
        setUploadLoading(false);
        setSuccess(`Successfully loaded ${parsedInstances.length} database instances`);
      },
      error: (error) => {
        setError('Error reading file: ' + error.message);
        setUploadLoading(false);
      }
    });
  };

  const handleUpgrade = async () => {
    // This function is now called from the old upgrade modal
    // Redirect to the new credentials modal system
    setShowUpgradeModal(false);
    handleUpgradeClick();
  };

  const tableColumns = [
    {
      id: 'database_name',
      header: 'Database Name',
      cell: item => (
        <div>
          <strong>{item.database_name}</strong>
          <Badge color={item.cluster_type === 'RDS' ? 'green' : 'blue'}>
            {item.cluster_type}
          </Badge>
        </div>
      ),
      sortingField: 'database_name'
    },
    {
      id: 'region',
      header: 'Region',
      cell: item => item.region,
      sortingField: 'region'
    },
    {
      id: 'current_version',
      header: 'Instance/Cluster',
      cell: item => (
        <Box>
          <div className="detail-value">
            {item.cluster_type === 'Aurora' ? item.aurora_cluster : item.rds_instance}
          </div>
        </Box>
      )
    },
    {
      id: 'target_version',
      header: 'Target Version',
      cell: item => (
        <Box>
          <div className="detail-value">{item.target_engine_version}</div>
          <div className="detail-label">Family: {item.target_parameter_family}</div>
        </Box>
      )
    },
    {
      id: 'backup_bucket',
      header: 'Backup Bucket',
      cell: item => item.bucket_name,
      sortingField: 'bucket_name'
    }
  ];

  return (
    <div className="app-layout">
      {authRequired && !authChecked && null}
      {authRequired && authChecked && !authenticated && (
        <Login onSignedIn={handleSignedIn} />
      )}
      {(!authRequired || authenticated) && (
      <>
      <TopNavigation />
      <AppLayout
        navigation={
          <SideNavigation 
            activeHref={activeHref} 
            onFollow={handleNavigationChange}
          />
        }
        navigationOpen={navigationOpen}
        onNavigationChange={({ detail }) => setNavigationOpen(detail.open)}
        tools={<HelpPanel />}
        toolsOpen={toolsOpen}
        onToolsChange={({ detail }) => setToolsOpen(detail.open)}
        content={
          <ContentLayout
            header={
              <Header
                variant="h1"
                description={activeHref === '#/config-generator'
                  ? 'Save credentials to Secrets Manager and configure network for ECS tasks'
                  : 'Upload your configuration file and select instances to upgrade'
                }
                actions={
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button iconName="menu" variant="icon" onClick={() => setNavigationOpen(!navigationOpen)} ariaLabel="Open navigation" />
                    <Button iconName="status-info" variant="icon" onClick={() => setToolsOpen(!toolsOpen)} ariaLabel="Open help panel" />
                    {authRequired && authenticated && (
                      <Button iconName="user-profile" onClick={handleSignOut}>
                        {currentUser ? `Sign out (${currentUser})` : 'Sign out'}
                      </Button>
                    )}
                  </SpaceBetween>
                }
              >
                {activeHref === '#/config-generator' ? 'Config Generator' : 'MySQL Database Upgrader'}
              </Header>
            }
          >
            {activeHref === '#/config-generator'
              ? <ConnectionSetup />
              : (
              <SpaceBetween direction="vertical" size="l">
              {/* Error/Success Messages */}
              {error && (
                <Alert type="error" dismissible onDismiss={() => setError('')}>
                  {error}
                </Alert>
              )}
              {success && (
                <Alert type="success" dismissible onDismiss={() => setSuccess('')}>
                  {success}
                </Alert>
              )}

              {/* V3 Processing Alert */}
              {summaryV3Loading && (
                <Alert 
                  type="info" 
                  header="🚀 AI Analysis in Progress"
                >
                  <div>
                    <strong>Gen AI Summary V3 is analyzing your database instances...</strong>
                  </div>
                  <div style={{ marginTop: '8px' }}>
                    ⏱️ <strong>Elapsed time:</strong> {v3ProcessingTime} seconds
                  </div>
                  <div style={{ marginTop: '8px', fontSize: '14px', color: '#666' }}>
                    ⚠️ <em>Note: API Gateway has a 30-second timeout limit. For longer analyses, consider using fewer instances or ask for async processing.</em>
                  </div>
                </Alert>
              )}

              {/* File Upload Section */}
              <Container header={<Header variant="h2">Upload Configuration File</Header>}>
                <SpaceBetween direction="vertical" size="m">
                  <FormField
                    label="CSV Configuration File"
                    description="Upload a CSV file containing database instance details"
                  >
                    <FileUpload
                      onChange={({ detail }) => handleFileUpload(detail)}
                      value={file}
                      i18nStrings={{
                        uploadButtonText: e => e ? "Choose files" : "Choose file",
                        dropzoneText: e => e ? "Drop files to upload" : "Drop file to upload",
                        removeFileAriaLabel: e => `Remove file ${e + 1}`,
                        limitShowFewer: "Show fewer files",
                        limitShowMore: "Show more files",
                        errorIconAriaLabel: "Error"
                      }}
                      showFileLastModified
                      showFileSize
                      showFileThumbnail
                      accept=".csv,.txt"
                      constraintText="CSV files only"
                    />
                  </FormField>
                  
                  {uploadLoading && (
                    <Box>
                      <ProgressBar
                        status="in-progress"
                        value={50}
                        additionalInfo="Parsing CSV file..."
                        description="Processing uploaded file"
                      />
                    </Box>
                  )}
                </SpaceBetween>
              </Container>

              {/* Instances Table Section */}
              {instances.length > 0 && (
                <Container 
                  header={
                    <Header 
                      variant="h2" 
                      counter={`(${instances.length})`}
                      actions={
                        <SpaceBetween direction="horizontal" size="xs">
                          <Button
                            onClick={() => setSelectedItems(instances)}
                            disabled={selectedItems.length === instances.length}
                          >
                            Select All
                          </Button>
                          <Button
                            onClick={() => setSelectedItems([])}
                            disabled={selectedItems.length === 0}
                          >
                            Clear Selection
                          </Button>
                        </SpaceBetween>
                      }
                    >
                      Database Instances
                    </Header>
                  }
                >
                  <SpaceBetween direction="vertical" size="m">
                    {selectedItems.length > 0 && (
                      <Alert type="info">
                        <strong>{selectedItems.length}</strong> of <strong>{instances.length}</strong> instances selected for upgrade
                      </Alert>
                    )}
                    
                    <Table
                      columnDefinitions={tableColumns}
                      items={instances}
                      loadingText="Loading instances"
                      selectionType="multi"
                      selectedItems={selectedItems}
                      onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
                      ariaLabels={{
                        selectionGroupLabel: "Items selection",
                        allItemsSelectionLabel: ({ selectedItems }) =>
                          `${selectedItems.length} ${
                            selectedItems.length === 1 ? "item" : "items"
                          } selected`,
                        itemSelectionLabel: ({ selectedItems }, item) => {
                          const isItemSelected = selectedItems.filter(
                            i => i.id === item.id
                          ).length;
                          return `${item.database_name} is ${
                            isItemSelected ? "" : "not "
                          }selected`;
                        }
                      }}
                      trackBy="id"
                      empty={
                        <Box textAlign="center" color="inherit">
                          <b>No instances</b>
                          <Box
                            padding={{ bottom: "s" }}
                            variant="p"
                            color="inherit"
                          >
                            No instances to display.
                          </Box>
                        </Box>
                      }
                      header={
                        <Header
                          counter={
                            selectedItems.length
                              ? `(${selectedItems.length}/${instances.length})`
                              : `(${instances.length})`
                          }
                        >
                          Select instances to upgrade
                        </Header>
                      }
                    />
                  </SpaceBetween>
                </Container>
              )}

              {/* Action Buttons Section */}
              {instances.length > 0 && (
                <Container header={<Header variant="h2">Database Actions</Header>}>
                  <SpaceBetween direction="vertical" size="m">
                    
                    {/* Debug Information - Remove in production */}
                    {process.env.NODE_ENV === 'development' && (
                      <Alert type="info">
                        <strong>Debug Info:</strong> {instances.length} total instances loaded, {selectedItems.length} selected
                        <Box marginTop="xs">
                          Selected IDs: {selectedItems.map(item => item.id).join(', ')}
                        </Box>
                        <Box marginTop="xs">
                          Expected HTML files: {selectedItems.map(item => {
                            const instance = instances.find(inst => inst.id === item.id);
                            return instance ? `${instance.database_name}-precheck-report.html` : 'unknown';
                          }).join(', ')}
                        </Box>
                      </Alert>
                    )}
                    
                    <Box textAlign="center">
                      <SpaceBetween direction="horizontal" size="m">
                        <Button
                          variant="normal"
                          onClick={handleTestConnectionClick}
                          disabled={testLoading || selectedItems.length === 0}
                          loading={testLoading}
                          iconName="check"
                        >
                          {testLoading ? 'Configuring...' : `Config Generator (${selectedItems.length})`}
                        </Button>
                        <Button
                          variant="normal"
                          onClick={handlePrecheckClick}
                          disabled={precheckLoading || selectedItems.length === 0}
                          loading={precheckLoading}
                          iconName="status-info"
                        >
                          {precheckLoading ? 'Generating Report...' : `Generate Precheck Report (${selectedItems.length})`}
                        </Button>
                        <Button
                          variant="normal"
                          onClick={handleSummaryV2Click}
                          disabled={summaryV2Loading || selectedItems.length === 0}
                          loading={summaryV2Loading}
                          iconName="gen-ai"
                        >
                          {summaryV2Loading ? 'AI Analysis...' : `Generate AI Summary (${selectedItems.length})`}
                        </Button>
                        <Button
                          variant="normal"
                          onClick={handleUpgradeClick}
                          disabled={upgradeLoading || selectedItems.length === 0}
                          loading={upgradeLoading}
                          iconName="upload"
                        >
                          {upgradeLoading ? 'Processing...' : `Apply BG Deployment (${selectedItems.length})`}
                        </Button>
                        <Button
                          variant="normal"
                          onClick={handleSwitchoverClick}
                          disabled={switchoverLoading || selectedItems.length === 0}
                          loading={switchoverLoading}
                          iconName="refresh"
                        >
                          {switchoverLoading ? 'Switching over...' : `Switchover (${selectedItems.length})`}
                        </Button>
                      </SpaceBetween>
                    </Box>
                  </SpaceBetween>
                </Container>
              )}
            </SpaceBetween>
              )}
          </ContentLayout>
        }
      />

      {/* Upgrade Confirmation Modal */}
      <Modal
        onDismiss={() => setShowUpgradeModal(false)}
        visible={showUpgradeModal}
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowUpgradeModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleUpgrade}>
                Confirm Upgrade
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Confirm Database Upgrade"
      >
        <SpaceBetween direction="vertical" size="m">
          <Box>
            <TextContent>
              <p>
                You are about to initiate an upgrade for <strong>{selectedItems.length}</strong> database instance(s).
                This action will send upgrade requests to your configured API endpoint.
              </p>
            </TextContent>
          </Box>
          
          <Container header={<Header variant="h3">Selected Instances</Header>}>
            <ColumnLayout columns={1} variant="text-grid">
              {selectedItems.map((item, index) => (
                <div key={item.id}>
                  <Box>
                    <strong>{item.database_name}</strong> ({item.cluster_type}) - {item.region}
                    <br />
                    <small>{item.rds_instance} → {item.target_engine_version}</small>
                  </Box>
                </div>
              ))}
            </ColumnLayout>
          </Container>

          <Alert type="warning">
            <strong>Important:</strong> Please ensure you have proper backups before proceeding with the upgrade.
            This action cannot be undone.
          </Alert>
        </SpaceBetween>
      </Modal>

      {/* Credentials Modal */}
      <CredentialsModal
        visible={showCredentialsModal}
        onDismiss={() => setShowCredentialsModal(false)}
        onConfirm={handleCredentialsConfirm}
        selectedInstances={selectedItems}
        actionType={currentAction}
        loading={currentAction === 'precheck' ? precheckLoading : currentAction === 'test' ? testLoading : upgradeLoading}
      />

      {/* Redesigned AI Summary Modal */}
      <RedesignedAISummaryModal
        visible={showSummaryModal}
        onDismiss={() => setShowSummaryModal(false)}
        summaryData={enhancedSummaryData || summaryData}
        selectedInstances={selectedItems}
      />

      {/* V2 Summary Modal */}
      <SummaryV2Modal
        visible={showSummaryV2Modal}
        onDismiss={() => setShowSummaryV2Modal(false)}
        summaryData={summaryV2Data}
      />

      {/* V3 Summary Modal */}
      <SummaryV3Modal
        visible={showSummaryV3Modal}
        onDismiss={() => setShowSummaryV3Modal(false)}
        summaryData={summaryV3Data}
      />

      {/* ECS Log Viewer Modal */}
      <ECSLogViewer
        visible={showLogViewer}
        onDismiss={() => setShowLogViewer(false)}
        taskArn={currentTaskArn}
        clusterName={currentClusterName}
        taskType={currentAction === 'precheck' ? 'prechecker' : currentAction === 'switchover' ? 'switchover' : 'upgrader'}
      />

      {/* Precheck Results Modal */}
      <PrecheckResultsModal
        visible={showPrecheckResultsModal}
        onDismiss={() => setShowPrecheckResultsModal(false)}
        selectedInstances={selectedItems.map(item => {
          const instance = instances.find(inst => inst.id === item.id);
          return instance;
        }).filter(Boolean)}
        precheckResponse={precheckResponse}
      />

      {/* Error Analysis Modal */}
      <ErrorAnalysisModal
        visible={showErrorAnalysis}
        onDismiss={() => setShowErrorAnalysis(false)}
        analysisData={errorAnalysisData}
      />

      </>
      )}
    </div>
  );
}

export default App;
