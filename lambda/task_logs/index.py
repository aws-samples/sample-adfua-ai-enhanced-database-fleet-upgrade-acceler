import json
import boto3
import os


CLUSTER_NAME         = os.environ['CLUSTER_NAME']
LOG_GROUP_PRECHECKER = f"/ecs/mysql-prechecker-{os.environ['AWS_ACCOUNT_ID']}"
LOG_GROUP_UPGRADER   = f"/ecs/mysql-upgrader-{os.environ['AWS_ACCOUNT_ID']}"
LOG_GROUP_SWITCHOVER = f"/ecs/mysql-switchover-{os.environ['AWS_ACCOUNT_ID']}"


def lambda_handler(event, context):
    body = event.get('body', '{}')
    if isinstance(body, str):
        body = json.loads(body)

    task_arn   = body.get('task_arn', '')
    task_type  = body.get('task_type', 'prechecker')  # 'prechecker' or 'upgrader'
    next_token = body.get('next_token')               # pagination token

    if not task_arn:
        return _resp(400, {'error': 'task_arn is required'})

    task_id    = task_arn.split('/')[-1]
    account_id = os.environ['AWS_ACCOUNT_ID']
    region     = os.environ.get('AWS_REGION', 'us-east-1')
    log_group = (
        LOG_GROUP_PRECHECKER if task_type == 'prechecker'
        else LOG_GROUP_SWITCHOVER if task_type == 'switchover'
        else LOG_GROUP_UPGRADER
    )
    container = (
        f"mysql-prechecker-{account_id}" if task_type == 'prechecker'
        else f"mysql-switchover-{account_id}" if task_type == 'switchover'
        else f"mysql-upgrader-{account_id}"
    )
    log_stream = f"ecs/{container}/{task_id}"

    logs_client = boto3.client('logs', region_name=region)
    ecs_client  = boto3.client('ecs',  region_name=region)

    # ── Task status ───────────────────────────────────────────────────────────
    task_status = 'UNKNOWN'
    stop_reason = None
    exit_code   = None
    try:
        resp = ecs_client.describe_tasks(cluster=CLUSTER_NAME, tasks=[task_arn])
        if resp['tasks']:
            task        = resp['tasks'][0]
            task_status = task.get('lastStatus', 'UNKNOWN')
            stop_reason = task.get('stoppedReason')
            containers  = task.get('containers', [])
            if containers:
                exit_code = containers[0].get('exitCode')
    except Exception:
        pass

    # ── Log events ────────────────────────────────────────────────────────────
    events    = []
    new_token = None
    log_exists = True
    try:
        kwargs = {
            'logGroupName':  log_group,
            'logStreamName': log_stream,
            'startFromHead': True,
            'limit':         200,
        }
        if next_token:
            kwargs['nextToken'] = next_token

        log_resp  = logs_client.get_log_events(**kwargs)
        events    = [{'timestamp': e['timestamp'], 'message': e['message']}
                     for e in log_resp.get('events', [])]
        new_token = log_resp.get('nextForwardToken')
    except logs_client.exceptions.ResourceNotFoundException:
        log_exists = False
    except Exception:
        log_exists = False

    return _resp(200, {
        'task_status': task_status,
        'stop_reason': stop_reason,
        'exit_code':   exit_code,
        'log_group':   log_group,
        'log_stream':  log_stream,
        'log_exists':  log_exists,
        'events':      events,
        'next_token':  new_token,
    })


def _resp(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps(body),
    }
