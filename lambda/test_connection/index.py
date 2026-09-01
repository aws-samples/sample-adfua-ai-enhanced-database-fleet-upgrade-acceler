import json
import boto3
import os

INTERFACE_SERVICES = ["ecr.dkr", "ecr.api", "logs", "ssm", "secretsmanager", "rds"]


# ── RDS discovery ─────────────────────────────────────────────────────────────

def get_rds_info(instance_name, cluster_type, region):
    rds = boto3.client('rds', region_name=region)
    if cluster_type == 'aurora':
        resp    = rds.describe_db_clusters(DBClusterIdentifier=instance_name)
        cluster = resp['DBClusters'][0]
        sg_resp = rds.describe_db_subnet_groups(DBSubnetGroupName=cluster['DBSubnetGroup'])
        sg      = sg_resp['DBSubnetGroups'][0]
        return (
            cluster['Endpoint'], cluster['Port'],
            sg['VpcId'], sg['Subnets'][0]['SubnetIdentifier'],
            cluster['VpcSecurityGroups'][0]['VpcSecurityGroupId'],
        )
    else:
        resp = rds.describe_db_instances(DBInstanceIdentifier=instance_name)
        db   = resp['DBInstances'][0]
        return (
            db['Endpoint']['Address'], db['Endpoint']['Port'],
            db['DBSubnetGroup']['VpcId'],
            db['DBSubnetGroup']['Subnets'][0]['SubnetIdentifier'],
            db['VpcSecurityGroups'][0]['VpcSecurityGroupId'],
        )


# ── Secret Manager ────────────────────────────────────────────────────────────

def save_secret(secret_name, username, password, region):
    sm  = boto3.client('secretsmanager', region_name=region)
    val = json.dumps({'username': username, 'password': password})
    try:
        sm.describe_secret(SecretId=secret_name)
        sm.put_secret_value(SecretId=secret_name, SecretString=val)
        return 'updated'
    except sm.exceptions.ResourceNotFoundException:
        sm.create_secret(
            Name=secret_name,
            Description=f"DB credentials for mysql-upgrader — {secret_name}",
            SecretString=val,
        )
        return 'created'


# ── Network provisioning ──────────────────────────────────────────────────────

def ensure_ecs_sg(vpc_id, section, region):
    ec2 = boto3.client('ec2', region_name=region)
    existing = ec2.describe_security_groups(Filters=[
        {'Name': 'vpc-id',                     'Values': [vpc_id]},
        {'Name': 'tag:mysql-upgrader-section', 'Values': [section]},
    ])['SecurityGroups']
    if existing:
        return existing[0]['GroupId']

    sg_id = ec2.create_security_group(
        GroupName=f"mysql-upgrader-ecs-sg-{section}",
        Description=f"ECS Fargate tasks for mysql-upgrader {section}",
        VpcId=vpc_id,
    )['GroupId']
    ec2.create_tags(Resources=[sg_id], Tags=[
        {'Key': 'Name',                   'Value': f"mysql-upgrader-ecs-sg-{section}"},
        {'Key': 'mysql-upgrader-section', 'Value': section},
    ])
    try:
        ec2.authorize_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[{'IpProtocol': '-1', 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}],
        )
    except Exception as e:
        if 'InvalidPermission.Duplicate' not in str(e):
            raise
    return sg_id


def open_sg_rule(group_id, port, source_sg_id, region):
    ec2 = boto3.client('ec2', region_name=region)
    try:
        ec2.authorize_security_group_ingress(
            GroupId=group_id,
            IpPermissions=[{
                'IpProtocol': 'tcp', 'FromPort': port, 'ToPort': port,
                'UserIdGroupPairs': [{'GroupId': source_sg_id}],
            }],
        )
    except Exception as e:
        if 'InvalidPermission.Duplicate' not in str(e):
            print(f"SG rule {port}: {e}")


def ensure_vpc_endpoints(vpc_id, rds_sg_id, ecs_sg_id, region):
    ec2 = boto3.client('ec2', region_name=region)

    main_rt = ec2.describe_route_tables(Filters=[
        {'Name': 'vpc-id',           'Values': [vpc_id]},
        {'Name': 'association.main', 'Values': ['true']},
    ])['RouteTables']
    main_rt_id = main_rt[0]['RouteTableId'] if main_rt else None

    subnets_by_az = {}
    for s in ec2.describe_subnets(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
    )['Subnets']:
        subnets_by_az.setdefault(s['AvailabilityZone'], s['SubnetId'])
    subnet_ids = list(subnets_by_az.values())

    for svc in INTERFACE_SERVICES:
        svc_name = f"com.amazonaws.{region}.{svc}"
        existing = ec2.describe_vpc_endpoints(Filters=[
            {'Name': 'vpc-id',             'Values': [vpc_id]},
            {'Name': 'service-name',       'Values': [svc_name]},
            {'Name': 'vpc-endpoint-state', 'Values': ['available', 'pending']},
        ])['VpcEndpoints']
        if not existing:
            ec2.create_vpc_endpoint(
                VpcId=vpc_id, ServiceName=svc_name,
                VpcEndpointType='Interface', SubnetIds=subnet_ids,
                SecurityGroupIds=[rds_sg_id, ecs_sg_id],
                PrivateDnsEnabled=True,
            )
        else:
            current_sgs = [g['GroupId'] for g in existing[0].get('Groups', [])]
            if ecs_sg_id not in current_sgs:
                try:
                    ec2.modify_vpc_endpoint(
                        VpcEndpointId=existing[0]['VpcEndpointId'],
                        AddSecurityGroupIds=[ecs_sg_id],
                    )
                except Exception as e:
                    if 'LimitExceeded' not in str(e) and 'NetworkInterfaceLimitExceeded' not in str(e):
                        raise
                    print(f"SG limit reached for {svc_name}, skipping — existing SGs should suffice")

    s3_svc = f"com.amazonaws.{region}.s3"
    s3_ep  = ec2.describe_vpc_endpoints(Filters=[
        {'Name': 'vpc-id',             'Values': [vpc_id]},
        {'Name': 'service-name',       'Values': [s3_svc]},
        {'Name': 'vpc-endpoint-state', 'Values': ['available', 'pending']},
    ])['VpcEndpoints']
    if not s3_ep:
        ec2.create_vpc_endpoint(
            VpcId=vpc_id, ServiceName=s3_svc,
            VpcEndpointType='Gateway',
            RouteTableIds=[main_rt_id] if main_rt_id else [],
        )
    elif main_rt_id:
        ec2.modify_vpc_endpoint(
            VpcEndpointId=s3_ep[0]['VpcEndpointId'],
            AddRouteTableIds=[main_rt_id],
        )


def write_ssm_params(section, subnet_id, ecs_sg_id, secret_name, region):
    ssm  = boto3.client('ssm', region_name=region)
    base = f"/mysql-upgrader/{section}"
    ssm.put_parameter(Name=f"{base}/ecs_subnet_id",           Value=subnet_id,   Type='String', Overwrite=True)
    ssm.put_parameter(Name=f"{base}/ecs_sg_id",               Value=ecs_sg_id,   Type='String', Overwrite=True)
    ssm.put_parameter(Name=f"{base}/credentials_secret_name", Value=secret_name, Type='String', Overwrite=True)


# ── Config.ini generation ─────────────────────────────────────────────────────

def build_and_upload_config(instance, bucket, secret_name, region):
    """Generate config.ini and upload to S3. Returns the S3 path."""
    instance_name = instance.get('rds_instance') or instance.get('aurora_cluster') or instance.get('database_name')
    cluster_type  = instance.get('cluster_type', 'rds').lower()
    section       = f"{instance_name}_config_details"

    lines = [
        f"[{section}]",
        f"cluster_type = {cluster_type}",
        f"region = {region}",
        f"rds_instance = {instance.get('rds_instance', instance_name)}",
        f"rds_instance_identifier = {instance.get('rds_instance', instance_name)}",
        f"target_parameter_family = {instance.get('target_parameter_family', 'mysql8.0')}",
        f"target_engine_version = {instance.get('target_engine_version', '8.0.35')}",
        f"credentials_secret_name = {secret_name}",
        f"bucket_name = {bucket}",
        f"app_bucket_name = {bucket}",
    ]
    s3_key = f"config/{instance_name}.ini"
    boto3.client('s3').put_object(
        Bucket=bucket, Key=s3_key,
        Body=("\n".join(lines) + "\n").encode('utf-8'),
        ContentType='text/plain',
    )
    config_s3_path = f"s3://{bucket}/{s3_key}"

    # Also store the config path in SSM so prechecker can find it directly
    ssm  = boto3.client('ssm', region_name=region)
    ssm.put_parameter(
        Name=f"/mysql-upgrader/{section}/config_s3_path",
        Value=config_s3_path,
        Type='String', Overwrite=True
    )
    return config_s3_path


# ── BG deployment check ───────────────────────────────────────────────────────

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


# ── Lambda handler ────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    body = event.get('body', '{}')
    if isinstance(body, str):
        body = json.loads(body)

    instances = body.get('instances', [])
    username  = body.get('username', '')
    password  = body.get('password', '')

    if not username or not password:
        return _resp(400, {'error': 'username and password are required'})

    bucket    = os.environ['S3_BUCKET']
    results   = []

    for instance in instances:
        instance_name = instance.get('rds_instance') or instance.get('aurora_cluster') or instance.get('database_name')
        cluster_type  = instance.get('cluster_type', 'rds').lower()
        region        = instance.get('region', 'us-east-1')
        secret_name   = instance.get('credentials_secret_name') or f"mysql-upgrader/{instance_name}/credentials"
        section       = f"{instance_name}_config_details"

        try:
            # Check if BG deployment already exists
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

            # 1. Verify RDS instance exists and get network info
            host, port, vpc_id, subnet_id, rds_sg_id = get_rds_info(instance_name, cluster_type, region)

            # 2. Save credentials to Secrets Manager
            secret_action = save_secret(secret_name, username, password, region)

            # 3. Provision network (idempotent — safe to call multiple times)
            ecs_sg_id = ensure_ecs_sg(vpc_id, section, region)
            open_sg_rule(rds_sg_id, 3306, ecs_sg_id, region)
            open_sg_rule(rds_sg_id, 443,  ecs_sg_id, region)
            ensure_vpc_endpoints(vpc_id, rds_sg_id, ecs_sg_id, region)

            # 4. Write SSM params
            write_ssm_params(section, subnet_id, ecs_sg_id, secret_name, region)

            # 5. Build config.ini and upload to S3 — prechecker uses this directly
            config_s3_path = build_and_upload_config(instance, bucket, secret_name, region)

            results.append({
                'database_name':   instance_name,
                'status':          'configured',
                'host':            host,
                'port':            port,
                'secret_name':     secret_name,
                'secret_action':   secret_action,
                'config_s3_path':  config_s3_path,
                'report_s3_path':  f"s3://{bucket}/precheck_report/{instance_name}-precheck-report.html",
                'message': (
                    f"RDS instance '{instance_name}' found at {host}:{port}. "
                    f"Credentials saved ({secret_action}). "
                    f"Config uploaded to S3. Ready to run precheck."
                ),
            })

        except Exception as e:
            results.append({
                'database_name': instance_name,
                'status':        'error',
                'error':         str(e),
                'error_type':    type(e).__name__,
            })

    return _resp(200, {'message': 'Configuration complete', 'results': results})


def _resp(status, body):
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(body),
    }
