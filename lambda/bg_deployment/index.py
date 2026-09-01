import json
import boto3
import os
import time

IN_PROGRESS_STATUSES = {
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
    """Check if a Blue/Green deployment already exists for this instance.
    Returns (exists: bool, deployment_info: dict or None)
    """
    rds = boto3.client('rds', region_name=region)
    try:
        response = rds.describe_blue_green_deployments()
        for dep in response.get('BlueGreenDeployments', []):
            source = dep.get('Source', '')
            name = dep.get('BlueGreenDeploymentName', '')
            status = dep.get('Status', '').upper()
            if (instance_name in source or instance_name in name) and status in IN_PROGRESS_STATUSES:
                return True, {
                    'deployment_id': dep['BlueGreenDeploymentIdentifier'],
                    'deployment_name': name,
                    'status': status,
                    'source': source,
                    'target': dep.get('Target', ''),
                    'message': STATUS_MESSAGES.get(status, f'Blue/Green deployment is in {status} state.'),
                }
    except Exception:
        pass
    return False, None


def get_task_config(instance_name, region):
    """Read subnet, ECS SG, and config path from SSM — written by Config Generator."""
    ssm     = boto3.client('ssm', region_name=region)
    section = f"{instance_name}_config_details"
    params  = ssm.get_parameters(
        Names=[
            f'/mysql-upgrader/{section}/ecs_subnet_id',
            f'/mysql-upgrader/{section}/ecs_sg_id',
            f'/mysql-upgrader/{section}/config_s3_path',
        ]
    )['Parameters']

    if len(params) < 3:
        raise ValueError(
            f"Config not found for '{instance_name}'. "
            "Please run 'Config Generator' first."
        )

    by_name        = {p['Name']: p['Value'] for p in params}
    subnet_id      = by_name[f'/mysql-upgrader/{section}/ecs_subnet_id']
    sg_id          = by_name[f'/mysql-upgrader/{section}/ecs_sg_id']
    config_s3_path = by_name[f'/mysql-upgrader/{section}/config_s3_path']
    return subnet_id, sg_id, config_s3_path


def lambda_handler(event, context):
    body = event.get('body', '{}')
    if isinstance(body, str):
        body = json.loads(body)

    instances    = body.get('instances', [])
    cluster_name = os.environ['CLUSTER_NAME']
    account_id   = os.environ['AWS_ACCOUNT_ID']
    results      = []

    for instance in instances:
        instance_name = instance.get('rds_instance') or instance.get('aurora_cluster') or instance.get('database_name')
        region        = instance.get('region', 'us-east-1')
        ecs           = boto3.client('ecs', region_name=region)

        try:
            # Check if BG deployment already exists or is in progress
            bg_exists, bg_info = check_existing_bg_deployment(instance_name, region)
            if bg_exists:
                results.append({
                    'database_name': instance_name,
                    'status':        'already_exists',
                    'message':       bg_info['message'],
                    'deployment_id': bg_info['deployment_id'],
                    'bg_status':     bg_info['status'],
                })
                continue

            # Read subnet, SG, and config path from SSM — all written by Config Generator
            subnet_id, sg_id, config_s3_path = get_task_config(instance_name, region)

            # Launch ECS Fargate upgrader task
            response = ecs.run_task(
                cluster=cluster_name,
                taskDefinition=f'mysql-upgrader-{account_id}',
                launchType='FARGATE',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets':        [subnet_id],
                        'securityGroups': [sg_id],
                        'assignPublicIp': 'DISABLED',
                    }
                },
                overrides={
                    'containerOverrides': [{
                        'name':    f'mysql-upgrader-{account_id}',
                        'command': [config_s3_path],
                    }]
                },
            )

            task_arn = response['tasks'][0]['taskArn']
            task_id  = task_arn.split('/')[-1]
            time.sleep(10)
            task = ecs.describe_tasks(cluster=cluster_name, tasks=[task_arn])['tasks'][0]

            results.append({
                'database_name':  instance_name,
                'task_arn':       task_arn,
                'task_id':        task_id,
                'task_status':    task['lastStatus'],
                'cluster_name':   cluster_name,
                'config_s3_path': config_s3_path,
                'status':         'started',
            })

        except Exception as e:
            results.append({
                'database_name': instance_name,
                'status':        'error',
                'error':         str(e),
                'error_type':    type(e).__name__,
            })

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({'message': 'Blue/Green deployment tasks initiated', 'results': results}),
    }
