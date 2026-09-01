import * as React from "react";
import {
  HelpPanel,
  Header,
  SpaceBetween,
  Box,
  Link,
  ExpandableSection,
  Alert
} from "@cloudscape-design/components";

export default function AppHelpPanel() {
  return (
    <HelpPanel
      header={<Header variant="h2">MySQL Database Upgrader Guide</Header>}
    >
      <SpaceBetween direction="vertical" size="m">
        
        <Alert type="info">
          <strong>Quick Start:</strong> Upload your CSV file, select instances, configure API endpoint, and initiate upgrade.
        </Alert>

        <ExpandableSection headerText="Step 1: Upload Configuration File" defaultExpanded>
          <SpaceBetween direction="vertical" size="s">
            <Box>
              <strong>Required CSV Format:</strong>
              <ul>
                <li><code>database_name</code> - Name of the database</li>
                <li><code>cluster_type</code> - RDS or Aurora</li>
                <li><code>region</code> - AWS region</li>
                <li><code>rds_instance</code> - Current version</li>
                <li><code>target_parameter_family</code> - Target parameter family</li>
                <li><code>target_engine_version</code> - Target version</li>
                <li><code>bucket_name</code> - S3 backup bucket</li>
              </ul>
            </Box>
            <Box>
              <strong>Tips:</strong>
              <ul>
                <li>Ensure all required columns are present</li>
                <li>Use consistent naming conventions</li>
                <li>Validate data before upload</li>
              </ul>
            </Box>
          </SpaceBetween>
        </ExpandableSection>

        <ExpandableSection headerText="Step 2: Select Database Instances">
          <SpaceBetween direction="vertical" size="s">
            <Box>
              <strong>Selection Options:</strong>
              <ul>
                <li>Individual selection via checkboxes</li>
                <li>Select All for bulk operations</li>
                <li>Filter by region or cluster type</li>
              </ul>
            </Box>
            <Box>
              <strong>Instance Information:</strong>
              <ul>
                <li>Current and target versions</li>
                <li>Region and cluster type</li>
                <li>Parameter family details</li>
                <li>Backup bucket configuration</li>
              </ul>
            </Box>
          </SpaceBetween>
        </ExpandableSection>

        <ExpandableSection headerText="Step 3: Configure API Endpoint">
          <SpaceBetween direction="vertical" size="s">
            <Box>
              <strong>API Configuration:</strong>
              <ul>
                <li>Enter your API Gateway endpoint URL</li>
                <li>Ensure proper authentication is configured</li>
                <li>Test connectivity before upgrade</li>
              </ul>
            </Box>
            <Box>
              <strong>Payload Structure:</strong>
              <pre style={{ fontSize: '12px', background: '#f5f5f5', padding: '8px' }}>
{`{
  "instances": [...],
  "action": "upgrade"
}`}
              </pre>
            </Box>
          </SpaceBetween>
        </ExpandableSection>

        <ExpandableSection headerText="Step 4: Initiate Upgrade">
          <SpaceBetween direction="vertical" size="s">
            <Box>
              <strong>Before Upgrading:</strong>
              <ul>
                <li>Verify backup configurations</li>
                <li>Review selected instances</li>
                <li>Confirm maintenance windows</li>
                <li>Check for dependencies</li>
              </ul>
            </Box>
            <Alert type="warning">
              <strong>Important:</strong> Database upgrades cannot be undone. Ensure proper backups are in place.
            </Alert>
          </SpaceBetween>
        </ExpandableSection>

        <ExpandableSection headerText="Best Practices">
          <SpaceBetween direction="vertical" size="s">
            <Box>
              <strong>Pre-Upgrade:</strong>
              <ul>
                <li>Test upgrades in non-production environments</li>
                <li>Create manual snapshots</li>
                <li>Review application compatibility</li>
                <li>Plan for rollback scenarios</li>
              </ul>
            </Box>
            <Box>
              <strong>During Upgrade:</strong>
              <ul>
                <li>Monitor upgrade progress</li>
                <li>Keep applications offline if needed</li>
                <li>Watch for error notifications</li>
              </ul>
            </Box>
            <Box>
              <strong>Post-Upgrade:</strong>
              <ul>
                <li>Verify database functionality</li>
                <li>Test application connections</li>
                <li>Monitor performance metrics</li>
                <li>Update parameter groups if needed</li>
              </ul>
            </Box>
          </SpaceBetween>
        </ExpandableSection>

        <ExpandableSection headerText="Troubleshooting">
          <SpaceBetween direction="vertical" size="s">
            <Box>
              <strong>Common Issues:</strong>
              <ul>
                <li><strong>CSV Parse Error:</strong> Check file format and encoding</li>
                <li><strong>API Connection Failed:</strong> Verify endpoint URL and authentication</li>
                <li><strong>Upgrade Failed:</strong> Check instance status and dependencies</li>
                <li><strong>Permission Denied:</strong> Verify IAM roles and policies</li>
              </ul>
            </Box>
            <Box>
              <strong>Getting Help:</strong>
              <ul>
                <li>Check upgrade logs for detailed error messages</li>
                <li>Review AWS CloudWatch logs</li>
                <li>Contact support team for assistance</li>
              </ul>
            </Box>
          </SpaceBetween>
        </ExpandableSection>

        <Box>
          <Header variant="h3">Additional Resources</Header>
          <SpaceBetween direction="vertical" size="xs">
            <Link external href="https://docs.aws.amazon.com/rds/latest/userguide/USER_UpgradeDBInstance.MySQL.html">
              AWS RDS MySQL Upgrade Guide
            </Link>
            <Link external href="https://dev.mysql.com/doc/refman/8.0/en/upgrading.html">
              MySQL 8.0 Upgrade Documentation
            </Link>
            <Link external href="https://docs.aws.amazon.com/rds/latest/userguide/USER_WorkingWithParamGroups.html">
              RDS Parameter Groups Guide
            </Link>
            <Link external href="https://docs.aws.amazon.com/rds/latest/userguide/USER_CreateSnapshot.html">
              Creating DB Snapshots
            </Link>
          </SpaceBetween>
        </Box>

      </SpaceBetween>
    </HelpPanel>
  );
}
