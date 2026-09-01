from config import APP_BUCKET_NAME
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    Duration,
    aws_s3 as s3,
    aws_s3_assets as s3_assets,
    aws_iam as iam,
    aws_amplify as amplify,
    aws_lambda as _lambda,
    custom_resources as cr,
)
from constructs import Construct
import json


class S3UiStack(Stack):
    """
    Hosts the React UI on AWS Amplify Hosting.

    CDK automatically deploys the UI on every cdk deploy:
      1. ui_build.zip (pre-built React app) is uploaded to S3 as a CDK asset
      2. A custom resource Lambda downloads the zip and uploads it to Amplify
      3. Amplify serves the built app via HTTPS with global CDN

    To update the UI:
      cd ui_source && npm run build
      cd build && zip -r ../../cdk/ui_build.zip .
      cdk deploy MysqlUpgraderUiStack
    """

    def __init__(self, scope: Construct, construct_id: str, api_url: str,
                 user_pool_id: str, user_pool_client_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        acct = self.account
        app_bucket_name = APP_BUCKET_NAME

        # ── Shared S3 bucket (config files + precheck reports) ────────────────
        # Finding #8: explicit SSE, TLS enforcement, and versioning enabled.
        app_bucket = s3.Bucket(
            self, "AppBucket",
            bucket_name=app_bucket_name,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── Pre-built UI zip as CDK S3 asset ──────────────────────────────────
        # CDK uploads ui_build.zip to the bootstrap bucket.
        # Hash changes when zip content changes → triggers redeploy.
        ui_asset = s3_assets.Asset(
            self, "UiSource",
            path="ui_build.zip",
        )

        # ── IAM role for Amplify ──────────────────────────────────────────────
        # Finding #4: replaced the broad AdministratorAccess-Amplify managed
        # policy with a minimal inline policy. This app deploys a pre-built zip
        # via a separate deploy Lambda (below) and uses no Amplify backend/build
        # features, so Amplify's service role only needs to write its own build
        # logs.
        amplify_role = iam.Role(
            self, "AmplifyRole",
            role_name=f"mysql-upgrader-amplify-role-{acct}",
            assumed_by=iam.ServicePrincipal("amplify.amazonaws.com"),
            inline_policies={
                "AmplifyBuildLogging": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AmplifyCloudWatchLogs",
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{acct}:log-group:/aws/amplify/*",
                            ],
                        ),
                    ]
                )
            },
        )

        # ── Amplify App ───────────────────────────────────────────────────────
        # Build spec is minimal — we deploy a pre-built zip, not source code.
        build_spec = json.dumps({
            "version": "1",
            "frontend": {
                "phases": {
                    "build": {"commands": ["echo Pre-built zip deployed via CDK"]},
                },
                "artifacts": {"baseDirectory": "/", "files": ["**/*"]},
            }
        })

        cfn_app = amplify.CfnApp(
            self, "AmplifyApp",
            name=f"mysql-upgrader-ui-{acct}",
            iam_service_role=amplify_role.role_arn,
            build_spec=build_spec,
            environment_variables=[
                amplify.CfnApp.EnvironmentVariableProperty(
                    name="REACT_APP_API_BASE",
                    value=api_url,
                ),
                amplify.CfnApp.EnvironmentVariableProperty(
                    name="REACT_APP_AWS_ACCOUNT_ID",
                    value=self.account,
                ),
                amplify.CfnApp.EnvironmentVariableProperty(
                    name="REACT_APP_AWS_REGION",
                    value=self.region,
                ),
                amplify.CfnApp.EnvironmentVariableProperty(
                    name="REACT_APP_USER_POOL_ID",
                    value=user_pool_id,
                ),
                amplify.CfnApp.EnvironmentVariableProperty(
                    name="REACT_APP_USER_POOL_CLIENT_ID",
                    value=user_pool_client_id,
                ),
            ],
            custom_rules=[
                amplify.CfnApp.CustomRuleProperty(
                    source="</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json)$)([^.]+$)/>",
                    target="/index.html",
                    status="200",
                )
            ],
        )

        cfn_branch = amplify.CfnBranch(
            self, "AmplifyMainBranch",
            app_id=cfn_app.attr_app_id,
            branch_name="main",
            stage="PRODUCTION",
            enable_auto_build=False,
        )

        # ── Deploy Lambda — downloads zip from S3 and pushes to Amplify ───────
        deploy_role = iam.Role(
            self, "AmplifyDeployRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            inline_policies={
                "AmplifyDeploy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["amplify:CreateDeployment", "amplify:StartDeployment"],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            actions=["s3:GetObject"],
                            resources=[f"{ui_asset.bucket.bucket_arn}/*"],
                        ),
                    ]
                )
            },
        )

        deploy_fn = _lambda.Function(
            self, "AmplifyDeployFn",
            function_name=f"mysql-upgrader-amplify-deploy-{acct}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            role=deploy_role,
            timeout=Duration.minutes(5),
            environment={
                "APP_ID":     cfn_app.attr_app_id,
                "BRANCH":     "main",
                "S3_BUCKET":  ui_asset.s3_bucket_name,
                "S3_KEY":     ui_asset.s3_object_key,
                "API_URL":    api_url,
                "ACCOUNT_ID": self.account,
                "REGION":     self.region,
                "USER_POOL_ID":        user_pool_id,
                "USER_POOL_CLIENT_ID": user_pool_client_id,
            },
            code=_lambda.Code.from_inline("""
import boto3, os, urllib.request, zipfile, io, json

def handler(event, context):
    if event.get('RequestType') == 'Delete':
        return {'PhysicalResourceId': event.get('PhysicalResourceId', 'delete')}

    app_id    = os.environ['APP_ID']
    branch    = os.environ['BRANCH']
    s3_bucket = os.environ['S3_BUCKET']
    s3_key    = os.environ['S3_KEY']
    api_url   = os.environ['API_URL']
    account_id = os.environ['ACCOUNT_ID']
    region     = os.environ.get('REGION', 'us-east-1')
    user_pool_id        = os.environ.get('USER_POOL_ID', '')
    user_pool_client_id = os.environ.get('USER_POOL_CLIENT_ID', '')

    # Get pre-signed upload URL from Amplify
    amplify_client = boto3.client('amplify')
    deploy = amplify_client.create_deployment(appId=app_id, branchName=branch)
    job_id     = deploy['jobId']
    upload_url = deploy['zipUploadUrl']

    # Download zip from CDK bootstrap bucket
    s3  = boto3.client('s3')
    obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    raw = obj['Body'].read()

    # Inject config.json with runtime values into the zip
    config_json = json.dumps({
        'REACT_APP_API_BASE': api_url,
        'REACT_APP_AWS_ACCOUNT_ID': account_id,
        'REACT_APP_AWS_REGION': region,
        'REACT_APP_USER_POOL_ID': user_pool_id,
        'REACT_APP_USER_POOL_CLIENT_ID': user_pool_client_id,
    })

    src = zipfile.ZipFile(io.BytesIO(raw), 'r')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        # Add config.json at the root of the zip
        dst.writestr('config.json', config_json)
    src.close()
    data = buf.getvalue()

    # Upload zip to Amplify pre-signed URL
    req = urllib.request.Request(upload_url, data=data, method='PUT')
    urllib.request.urlopen(req)

    # Start the deployment
    amplify_client.start_deployment(appId=app_id, branchName=branch, jobId=job_id)
    print(f"Amplify deployment started: job {job_id}, API URL: {api_url}")
    return {'PhysicalResourceId': f'amplify-deploy-{job_id}'}
"""),
        )

        # Grant deploy Lambda read access to the ui asset in bootstrap bucket
        ui_asset.bucket.grant_read(deploy_role)

        # ── Custom resource — invokes deploy Lambda on every cdk deploy ───────
        # physical_resource_id includes asset hash so it re-triggers when
        # ui_build.zip content changes.
        cr.AwsCustomResource(
            self, "AmplifyDeployTrigger",
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={"FunctionName": deploy_fn.function_name},
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"amplify-deploy-{ui_asset.asset_hash}"
                ),
            ),
            on_update=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={"FunctionName": deploy_fn.function_name},
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"amplify-deploy-{ui_asset.asset_hash}"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[deploy_fn.function_arn],
                )
            ]),
            timeout=Duration.minutes(10),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "UiBucketName",
            value=app_bucket.bucket_name,
            export_name=f"MysqlUpgraderAppBucketName-{acct}",
        )
        CfnOutput(self, "AmplifyAppId",
            value=cfn_app.attr_app_id,
            export_name=f"MysqlUpgraderAmplifyAppId-{acct}",
        )
        CfnOutput(self, "AmplifyAppUrl",
            value=f"https://main.{cfn_app.attr_default_domain}",
            description="React app URL via Amplify Hosting",
            export_name=f"MysqlUpgraderUiUrl-{acct}",
        )
