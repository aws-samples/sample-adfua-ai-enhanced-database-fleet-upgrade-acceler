import json
import boto3
import os
import time


def get_task_config(instance_name, region):
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
            subnet_id, sg_id, config_s3_path = get_task_config(instance_name, region)

            response = ecs.run_task(
                cluster=cluster_name,
                taskDefinition=f'mysql-switchover-{account_id}',
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
                        'name':    f'mysql-switchover-{account_id}',
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
                'status':         'switchover_initiated',
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
        'body': json.dumps({'message': 'Switchover tasks initiated', 'results': results}),
    }
