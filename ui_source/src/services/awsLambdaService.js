import axios from 'axios';
import { getApiBase } from '../config';

export const generateAISummaryDirect = async (selectedInstancesData) => {
  const API_BASE = getApiBase();
  const startTime = Date.now();
  try {
    const response = await axios.post(`${API_BASE}/genai-summary`, {
      database_names: selectedInstancesData.map(i => i.rds_instance || i.aurora_cluster || i.database_name),
      instances: selectedInstancesData,
      action: 'summary'
    }, { timeout: 300000 });

    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    return { success: true, data: response.data, statusCode: 200, duration };
  } catch (error) {
    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    return { success: false, error: error.message, errorType: 'APIError', duration };
  }
};

export const testLambdaConnection = async () => {
  const API_BASE = getApiBase();
  try {
    const response = await axios.post(`${API_BASE}/genai-summary`, {
      database_names: ['test'], action: 'summary', test_mode: true
    }, { timeout: 10000 });
    return { success: true, message: 'API is accessible' };
  } catch (error) {
    return { success: false, error: error.message };
  }
};

export const invokeLambdaDirectly = generateAISummaryDirect;
