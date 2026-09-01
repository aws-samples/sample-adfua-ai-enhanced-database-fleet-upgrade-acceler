import json
import boto3
import os
import re


S3_BUCKET = os.environ['S3_BUCKET']
BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

BG_ACTIVE_STATUSES = {
    'PROVISIONING', 'AVAILABLE', 'SWITCHOVER_IN_PROGRESS',
    'SWITCHOVER_COMPLETED'
}

STATUS_MESSAGES = {
    'PROVISIONING': 'Blue/Green deployment is currently in progress — green instance is being provisioned.',
    'AVAILABLE': 'Blue/Green deployment is already created and available — green instance is ready.',
    'SWITCHOVER_IN_PROGRESS': 'Blue/Green switchover is currently in progress — traffic is being moved to the green instance.',
    'SWITCHOVER_COMPLETED': 'Blue/Green switchover has been completed successfully.',
}


def check_existing_bg_deployment(instance_name, region):
    rds = boto3.client('rds', region_name=region)
    try:
        response = rds.describe_blue_green_deployments()
        for dep in response.get('BlueGreenDeployments', []):
            source = dep.get('Source', '')
            name = dep.get('BlueGreenDeploymentName', '')
            status = dep.get('Status', '').upper()
            if (instance_name in source or instance_name in name) and status in BG_ACTIVE_STATUSES:
                return True, {
                    'deployment_id': dep['BlueGreenDeploymentIdentifier'],
                    'status': status,
                    'message': STATUS_MESSAGES.get(status, f'Blue/Green deployment is in {status} state.'),
                }
    except Exception:
        pass
    return False, None


def get_report_from_s3(instance_name: str) -> str:
    s3 = boto3.client('s3')
    key = f"precheck_report/{instance_name}-precheck-report.html"
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        html = obj['Body'].read().decode('utf-8')
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:12000]
    except Exception as e:
        return f"Error reading report for {instance_name}: {str(e)}"


def analyze_with_bedrock(report_text: str, instance_names: list) -> dict:
    bedrock = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-east-1'))

    prompt = f"""Read this MySQL 5.7→8.0 precheck report for {', '.join(instance_names)} and generate SQL fixes.

{report_text}

Return JSON only. No markdown. Each remediation_steps entry = one issue with ALL SQL using REAL names from the report. NO placeholders.

{{
  "executive_summary": "Short: X errors, Y warnings. Ready/Not ready.",
  "risk_assessment": ["[CRITICAL] issue", "[WARNING] issue"],
  "remediation_steps": [
    "-- FIX: Title (N affected)\\nALTER TABLE `real_name` ...;\\nALTER TABLE `real_name2` ...;"
  ],
  "upgrade_strategy": ["Step 1: Backup", "Step 2: Fix critical", "Step 3: Fix warnings", "Step 4: Re-run precheck", "Step 5: Upgrade"],
  "timeline_sequence": ["Phase 1: Backup (10min)", "Phase 2: Fixes (1hr)", "Phase 3: Validate (10min)", "Phase 4: Upgrade (30min)"],
  "post_upgrade_verification": ["SELECT VERSION();"]
}}

Rules:
- Use ONLY names from the report. Never invent names.
- Each remediation_steps entry: one issue, ALL affected objects, complete SQL.
- Combine multiple column fixes into one ALTER TABLE statement per table: ALTER TABLE `t` MODIFY `c1` INT, MODIFY `c2` BIGINT;
- Skip RDS system users (rdsadmin, rdsrepladmin, mysql.sys, mysql.session, mysql.infoschema).
- If report says PASSWORD() but no procedure name: give SELECT to find it.
- Be concise. SQL only. No explanations inside SQL blocks."""

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response['body'].read())
    content = result['content'][0]['text']

    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        raw = json_match.group()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
            try:
                parsed = json.loads(fixed)
            except json.JSONDecodeError:
                return {"executive_summary": content, "risk_assessment": [], "remediation_steps": [], "upgrade_strategy": [], "timeline_sequence": [], "post_upgrade_verification": []}
        # Handle double-nested JSON (model returned JSON string as executive_summary)
        es = parsed.get('executive_summary', '')
        if isinstance(es, str) and es.strip().startswith('{'):
            try:
                inner = json.loads(es)
                if isinstance(inner, dict) and 'remediation_steps' in inner:
                    parsed = inner
            except json.JSONDecodeError:
                # Raw newlines in strings — escape them
                try:
                    inner = json.loads(es.replace('\n', '\\n').replace('\t', '\\t'))
                    if isinstance(inner, dict) and 'remediation_steps' in inner:
                        parsed = inner
                except Exception:
                    pass
        # Ensure strings
        for key in ['risk_assessment', 'remediation_steps', 'upgrade_strategy', 'timeline_sequence', 'post_upgrade_verification']:
            if key in parsed and isinstance(parsed[key], list):
                parsed[key] = [str(item) if not isinstance(item, str) else item for item in parsed[key]]
        if 'executive_summary' in parsed and not isinstance(parsed['executive_summary'], str):
            parsed['executive_summary'] = str(parsed['executive_summary'])
        # Split if model merged fixes into one entry
        if 'remediation_steps' in parsed and isinstance(parsed['remediation_steps'], list):
            expanded = []
            for step in parsed['remediation_steps']:
                parts = re.split(r'(?=-- FIX[ :])', str(step))
                expanded.extend([p.strip() for p in parts if p.strip()])
            # Format each fix
            formatted = []
            for step in expanded:
                lines = step.split('\n')
                title = lines[0].replace('-- ', '').strip()
                sql = [l.strip() for l in lines[1:] if l.strip() and not l.strip().startswith('--')]
                comments = [l.strip().lstrip('- ') for l in lines[1:] if l.strip().startswith('--')]
                block = f"\n{'━' * 60}\n  {title}\n{'━' * 60}\n"
                if comments:
                    block += ''.join(f'  {c}\n' for c in comments)
                if sql:
                    block += f"\n  ► SQL (copy and run):\n  {'─' * 40}\n"
                    block += ''.join(f'    {s}\n' for s in sql)
                    block += f"  {'─' * 40}\n"
                formatted.append(block)
            parsed['remediation_steps'] = formatted
        return parsed
    return {"executive_summary": content, "risk_assessment": [], "remediation_steps": [], "upgrade_strategy": [], "timeline_sequence": [], "post_upgrade_verification": []}


def lambda_handler(event, context):
    body = event.get('body', '{}')
    if isinstance(body, str):
        body = json.loads(body)

    instances = body.get('instances', [])
    database_names = body.get('database_names', [
        i.get('rds_instance') or i.get('aurora_cluster') or i.get('database_name')
        for i in instances
    ])

    if not database_names:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'No database names provided'}),
        }

    # Check for existing BG deployments
    region = os.environ.get('AWS_REGION', 'us-east-1')
    bg_warnings = []
    for name in database_names:
        if name:
            bg_exists, bg_info = check_existing_bg_deployment(name, region)
            if bg_exists:
                bg_warnings.append({
                    'database_name': name,
                    'message': bg_info['message'],
                    'deployment_id': bg_info['deployment_id'],
                    'bg_status': bg_info['status'],
                })

    # If ALL instances have BG deployments, return warning only
    if bg_warnings and len(bg_warnings) == len([n for n in database_names if n]):
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'status': 'already_exists',
                'bg_warnings': bg_warnings,
                'message': 'Blue/Green deployment already active for all selected instances.',
            }),
        }

    combined_report = ""
    for name in database_names:
        if name:
            combined_report += f"\n=== {name} ===\n{get_report_from_s3(name)}"

    try:
        analysis = analyze_with_bedrock(combined_report, database_names)
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'summary': analysis}),
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e), 'error_type': type(e).__name__}),
        }
