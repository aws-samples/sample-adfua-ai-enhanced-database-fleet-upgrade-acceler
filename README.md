# MySQL Upgrade Accelerator (ADUA)

Automated tool for upgrading Amazon RDS MySQL and Aurora MySQL databases using Blue/Green deployments, with pre-upgrade compatibility checks and AI-powered analysis.
---
## Architecture

| Stack | Resources |
|---|---|
| `MysqlUpgraderEcsStack` | ECR repos, ECS Fargate cluster, task definitions, CodeBuild (builds Docker images automatically) |
| `MysqlUpgraderApiStack` | 6 Lambda functions + API Gateway (7 routes) |
| `MysqlUpgraderUiStack` | S3 bucket, Amplify Hosting (serves React UI) |
---

## Prerequisites

| Tool | Install / Check |
|---|---|
| Python 3.9+ | `python3 --version` |
| Node.js 18+ | `node --version` (needed to build UI) |
| AWS CLI v2 | `aws --version` |
| AWS CDK CLI | `npm install -g aws-cdk` |
| AWS Profile | `aws configure --profile <your-profile>` |

> Docker Desktop is **not required** — images are built in AWS via CodeBuild.

---

## Step 1 — Clone and Configure

```bash
git clone <repo-url>
cd develop
```

Edit `config.py` with your AWS account details:

```python
AWS_ACCOUNT     = "123456789012"        # Your 12-digit AWS account ID
AWS_REGION      = "us-east-1"           # Target region
APP_BUCKET_NAME = f"adua-mysql-upgrade-{AWS_ACCOUNT}"
```

---

## Step 2 — Set Up Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 3 — Bootstrap CDK (one-time per account/region)

```bash
cdk bootstrap aws://<ACCOUNT_ID>/<REGION> --profile <your-profile>
```

---

## Step 4 — Build the UI

The React source lives in `ui_source/` inside this project.

```bash
cd ui_source
npm ci
REACT_APP_API_BASE=https://placeholder.execute-api.us-east-1.amazonaws.com/dev/ \
REACT_APP_AWS_ACCOUNT_ID=<ACCOUNT_ID> \
npm run build

# Zip from inside build/ so index.html is at the root
cd build && zip -r ../../ui_build.zip . && cd ../..
```

> For the first deploy, use a placeholder API URL. After deploy, get the real URL from the output and redeploy the UI stack.

---

## Step 5 — Deploy All Stacks

```bash
cd develop
source .venv/bin/activate
cdk deploy --all --profile <your-profile>
```

Deployment takes ~10-15 minutes. CDK deploys stacks in dependency order:
1. **EcsStack** → ECR repos + CodeBuild builds Docker images
2. **ApiStack** → Lambda functions + API Gateway
3. **UiStack** → S3 bucket + Amplify app deployment

---

## Step 6 — Redeploy UI with Real API URL (first time only)

After the first deploy, grab the API URL from the output:

```bash
aws cloudformation describe-stacks --stack-name MysqlUpgraderApiStack \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text \
  --profile <your-profile>
```

Rebuild the UI with the real API URL:

```bash
cd ui_source
REACT_APP_API_BASE=<real-api-url> \
REACT_APP_AWS_ACCOUNT_ID=<ACCOUNT_ID> \
npm run build
cd build && zip -r ../../ui_build.zip . && cd ../..

cdk deploy MysqlUpgraderUiStack --profile <your-profile>
```

---

## Step 7 — Enable Bedrock Model Access

In AWS Console → **Amazon Bedrock** → **Model access** → Request access for:
- **Claude 3 Sonnet** (`anthropic.claude-3-sonnet-20240229-v1:0`)

Required for the AI Summary feature.

---

## Using the Application

Open the Amplify URL from the deploy output (`AmplifyAppUrl`).

### 1. Prepare CSV Input

```csv
database_name,cluster_type,region,rds_instance,target_parameter_family,target_engine_version
my-db,rds,us-east-1,my-rds-instance,mysql8.0,8.0.35
my-aurora,aurora,us-east-1,my-aurora-cluster,aurora-mysql8.0,8.0.mysql_aurora.3.04.0
```

### 2. Config Generator (run once per RDS instance)

UI → **Config Generator** tab → upload CSV → enter DB credentials → **Generate Config**

This automatically:
- Verifies the RDS instance and discovers its VPC/subnet/SG
- Saves credentials to Secrets Manager
- Creates VPC endpoints (ECR, S3, CloudWatch, SSM, Secrets Manager, RDS)
- Opens port 3306 between ECS and RDS security groups
- Writes SSM parameters and uploads `config.ini` to S3

### 3. Run Pre-check

UI → **Upload Configuration** tab → upload CSV → select instances → **Generate Precheck Report**

ECS task connects to MySQL inside the VPC, runs compatibility checks, generates an HTML report in S3.

### 4. AI Summary

Select instances → **Generate AI Summary**

Reads the HTML report, sends to Bedrock Claude 3, returns structured analysis with recommendations.

### 5. Upgrade (Blue/Green Deployment)

Select instances → **Upgrade Selected Instances**

Creates a Blue/Green deployment, waits for sync, then you can trigger switchover when ready.

---

## Project Structure

```
develop/
├── app.py                  # CDK app entry point
├── config.py               # Account/region configuration (edit this)
├── cdk.json                # CDK settings
├── requirements.txt        # Python dependencies
├── stacks/
│   ├── api_stack.py        # Lambda + API Gateway
│   ├── ecs_stack.py        # ECR + ECS + CodeBuild
│   └── s3_ui_stack.py      # S3 + Amplify Hosting
├── lambda/
│   ├── bg_deployment/      # Blue/Green deployment trigger
│   ├── genai_summary/      # Bedrock AI analysis
│   ├── prechecker/         # ECS precheck trigger
│   ├── switchover/         # Blue/Green switchover
│   ├── task_logs/          # ECS task log retrieval
│   └── test_connection/    # RDS connectivity test
├── docker/
│   ├── prechecker/         # Precheck ECS container
│   ├── upgrader/           # Upgrade ECS container
│   └── switchover/         # Switchover ECS container
└── ui_source/              # React frontend source
    ├── src/
    ├── public/
    └── package.json
```

---

## Deploying to a Different Account

1. Update `config.py` with the new account ID and region
2. Run `cdk bootstrap` for the new account
3. Rebuild UI with new account ID
4. Run `cdk deploy --all`

All resource names are suffixed with the account number — no conflicts across accounts.

---

## Updating After Code Changes

**Lambda/Stack changes:**
```bash
cdk deploy --all --profile <your-profile>
```

**UI changes only:**
```bash
cd ui_source && npm run build
cd build && zip -r ../../ui_build.zip . && cd ../..
cdk deploy MysqlUpgraderUiStack --profile <your-profile>
```

**Docker image changes:**
```bash
cdk deploy MysqlUpgraderEcsStack --profile <your-profile>
```
CodeBuild automatically rebuilds and pushes images when source changes.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `Config not found for 'xxx'` | Run Config Generator first for that RDS instance |
| `CannotPullContainerError` | VPC endpoints missing — run Config Generator |
| `ResourceInitializationError` | CloudWatch Logs VPC endpoint missing — run Config Generator |
| `AI Summary: No report found` | Run precheck first to generate the HTML report |
| `Bedrock: AccessDeniedException` | Enable Claude 3 Sonnet in Bedrock Model Access (Step 7) |
| `CodeBuild: FAILED` | Check `/codebuild/mysql-upgrader-*` log groups in CloudWatch |
| `cdk deploy` fails with bootstrap error | Run `cdk bootstrap` (Step 3) |

---

## Cleanup

To destroy all resources:

```bash
cdk destroy --all --profile <your-profile>
```

> Note: ECR repositories and S3 bucket have `RETAIN` removal policy — delete them manually from the console if needed.
