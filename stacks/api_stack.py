from config import APP_BUCKET_NAME, UI_ALLOWED_ORIGINS, COGNITO_INITIAL_USER_EMAIL
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    BundlingOptions,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct
import jsii


@jsii.implements(cdk.ILocalBundling)
class _LocalPipBundler:
    """Installs requirements.txt locally then copies source. Falls back to Docker."""
    def try_bundle(self, output_dir: str, options) -> bool:
        import subprocess, shutil, os
        src = os.path.join(os.getcwd(), 'lambda', 'test_connection')
        req = os.path.join(src, 'requirements.txt')
        if not os.path.exists(req):
            return False
        try:
            subprocess.run(
                ['pip', 'install', '-r', req, '-t', output_dir, '-q'],
                check=True
            )
            for f in os.listdir(src):
                s = os.path.join(src, f)
                if os.path.isfile(s):
                    shutil.copy2(s, os.path.join(output_dir, f))
            return True
        except Exception:
            return False


class ApiStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        acct = self.account
        app_bucket_name = APP_BUCKET_NAME

        # ── Shared Lambda execution role ──────────────────────────────────────
        lambda_role = iam.Role(
            self, "MysqlUpgraderLambdaRole",
            role_name=f"mysql-upgrader-lambda-role-{acct}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            inline_policies={
                "MysqlUpgraderInlinePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="ECSAccess",
                            actions=["ecs:RunTask", "ecs:DescribeTasks", "ecs:DescribeClusters"],
                            # Scope to this account's ECS resources in this region.
                            resources=[
                                f"arn:aws:ecs:{self.region}:{acct}:task-definition/mysql-*",
                                f"arn:aws:ecs:{self.region}:{acct}:task/mysql-upgrade-cluster-{acct}/*",
                                f"arn:aws:ecs:{self.region}:{acct}:cluster/mysql-upgrade-cluster-{acct}",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="PassRoleToECS",
                            actions=["iam:PassRole"],
                            # Only the two ECS roles this app uses may be passed,
                            # and only to the ECS tasks service (blocks privilege
                            # escalation via passing arbitrary/admin roles).
                            resources=[
                                f"arn:aws:iam::{acct}:role/mysql-upgrader-ecs-execution-role-{acct}",
                                f"arn:aws:iam::{acct}:role/mysql-upgrader-ecs-task-role-{acct}",
                            ],
                            conditions={
                                "StringEquals": {
                                    "iam:PassedToService": "ecs-tasks.amazonaws.com"
                                }
                            },
                        ),
                        iam.PolicyStatement(
                            sid="CloudWatchLogs",
                            actions=["logs:GetLogEvents", "logs:DescribeLogStreams"],
                            resources=[
                                f"arn:aws:logs:{self.region}:{acct}:log-group:/ecs/mysql-*:*",
                                f"arn:aws:logs:{self.region}:{acct}:log-group:/aws/lambda/mysql-upgrader-*:*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="SSMReadNetworkConfig",
                            actions=["ssm:GetParameter", "ssm:GetParameters"],
                            resources=[
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/mysql-upgrader/*"
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="S3Access",
                            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                            resources=[
                                f"arn:aws:s3:::{app_bucket_name}",
                                f"arn:aws:s3:::{app_bucket_name}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="BedrockInvoke",
                            actions=["bedrock:InvokeModel"],
                            # Bedrock InvokeModel authorizes on the foundation-model ARN.
                            resources=[
                                f"arn:aws:bedrock:{self.region}::foundation-model/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="RDSDescribe",
                            # Read-only RDS describe actions do not support
                            # resource-level scoping for all APIs; kept broad but
                            # separated from mutating actions below.
                            actions=[
                                "rds:DescribeDBInstances",
                                "rds:DescribeDBClusters",
                                "rds:DescribeBlueGreenDeployments",
                                "rds:DescribeDBSnapshots",
                                "rds:DescribeDBSubnetGroups",
                            ],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            sid="RDSMutate",
                            # Destructive/mutating RDS actions scoped to this
                            # account's RDS resources in this region only.
                            actions=[
                                "rds:CreateBlueGreenDeployment",
                                "rds:SwitchoverBlueGreenDeployment",
                                "rds:DeleteBlueGreenDeployment",
                                "rds:CreateDBSnapshot",
                                "rds:CreateDBParameterGroup",
                                "rds:ModifyDBParameterGroup",
                            ],
                            resources=[
                                f"arn:aws:rds:{self.region}:{acct}:db:*",
                                f"arn:aws:rds:{self.region}:{acct}:cluster:*",
                                f"arn:aws:rds:{self.region}:{acct}:snapshot:*",
                                f"arn:aws:rds:{self.region}:{acct}:pg:*",
                                f"arn:aws:rds:{self.region}:{acct}:cluster-pg:*",
                                f"arn:aws:rds:{self.region}:{acct}:deployment:*",
                                f"arn:aws:rds:{self.region}:{acct}:blue-green-deployment:*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="SecretsManagerRead",
                            actions=[
                                "secretsmanager:GetSecretValue",
                                "secretsmanager:CreateSecret",
                                "secretsmanager:PutSecretValue",
                                "secretsmanager:DescribeSecret",
                            ],
                            # Scope to this app's secret namespace only.
                            resources=[
                                f"arn:aws:secretsmanager:{self.region}:{acct}:secret:mysql-upgrader/*",
                            ],
                        ),
                        # EC2 permissions for auto-provisioning VPC endpoints
                        # and security groups on first run per RDS instance.
                        # EC2 network APIs operate on resources discovered at
                        # runtime (arbitrary customer VPCs), so resource ARNs
                        # cannot be enumerated at deploy time. Blast radius is
                        # constrained to the deployment region.
                        iam.PolicyStatement(
                            sid="EC2NetworkProvisioning",
                            actions=[
                                "ec2:DescribeVpcs",
                                "ec2:DescribeSubnets",
                                "ec2:DescribeSecurityGroups",
                                "ec2:DescribeRouteTables",
                                "ec2:DescribeVpcEndpoints",
                                "ec2:CreateSecurityGroup",
                                "ec2:CreateTags",
                                "ec2:AuthorizeSecurityGroupIngress",
                                "ec2:AuthorizeSecurityGroupEgress",
                                "ec2:CreateVpcEndpoint",
                                "ec2:ModifyVpcEndpoint",
                            ],
                            resources=["*"],
                            conditions={
                                "StringEquals": {"aws:RequestedRegion": self.region}
                            },
                        ),
                        iam.PolicyStatement(
                            sid="SSMWriteNetworkConfig",
                            actions=["ssm:PutParameter"],
                            resources=[
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/mysql-upgrader/*"
                            ],
                        ),
                    ]
                )
            },
        )

        # ── Common Lambda settings ────────────────────────────────────────────
        common_lambda_props = dict(
            runtime=_lambda.Runtime.PYTHON_3_12,
            role=lambda_role,
            environment={
                "CLUSTER_NAME":    f"mysql-upgrade-cluster-{acct}",
                "S3_BUCKET":       app_bucket_name,
                "AWS_ACCOUNT_ID":  self.account,
            },
        )

        # ── Lambda functions ──────────────────────────────────────────────────
        prechecker_fn = _lambda.Function(
            self, "PrecheckerLambda",
            function_name=f"mysql-upgrader-{acct}",
            description="Triggers ECS Fargate prechecker task for MySQL upgrade compatibility check",
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda/prechecker"),
            timeout=Duration.seconds(120),
            memory_size=256,
            **common_lambda_props,
        )

        bg_deployment_fn = _lambda.Function(
            self, "BgDeploymentLambda",
            function_name=f"mysql-upgrader-bg-deployment-{acct}",
            description="Triggers ECS Fargate Blue/Green deployment task for MySQL upgrade",
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda/bg_deployment"),
            timeout=Duration.seconds(600),
            memory_size=256,
            **common_lambda_props,
        )

        genai_summary_fn = _lambda.Function(
            self, "GenAiSummaryLambda",
            function_name=f"mysql-upgrader-genai-summary-{acct}",
            description="Reads precheck HTML report from S3 and generates AI analysis using Bedrock Claude 3",
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda/genai_summary"),
            timeout=Duration.seconds(900),
            memory_size=512,
            **common_lambda_props,
        )

        task_logs_fn = _lambda.Function(
            self, "TaskLogsLambda",
            function_name=f"mysql-upgrader-task-logs-{acct}",
            description="Returns ECS task status and CloudWatch logs for real-time monitoring",
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda/task_logs"),
            timeout=Duration.seconds(30),
            memory_size=256,
            **common_lambda_props,
        )

        test_connection_fn = _lambda.Function(
            self, "TestConnectionLambda",
            function_name=f"mysql-upgrader-test-connection-{acct}",
            description="Tests RDS connection, creates Secrets Manager secret, validates credentials",
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset(
                "lambda/test_connection",
            ),
            timeout=Duration.seconds(300),  # VPC attachment ~30s + connection test
            memory_size=256,
            **common_lambda_props,
        )

        switchover_fn = _lambda.Function(
            self, "SwitchoverLambda",
            function_name=f"mysql-upgrader-switchover-{acct}",
            description="Triggers Blue/Green switchover for a completed deployment",
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda/switchover"),
            timeout=Duration.seconds(60),
            memory_size=256,
            **common_lambda_props,
        )

        # ── Cognito User Pool (authentication for the API) ────────────────────
        # Finding #1: the API previously had no authorizer (auth = NONE), so any
        # anonymous caller could invoke destructive endpoints. All methods now
        # require a valid Cognito-issued JWT.
        user_pool = cognito.UserPool(
            self, "MysqlUpgraderUserPool",
            user_pool_name=f"mysql-upgrader-users-{acct}",
            self_sign_up_enabled=False,          # operators are provisioned, not self-service
            sign_in_aliases=cognito.SignInAliases(email=True, username=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        user_pool_client = user_pool.add_client(
            "MysqlUpgraderUserPoolClient",
            user_pool_client_name=f"mysql-upgrader-web-{acct}",
            generate_secret=False,               # public SPA client — no client secret
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=True,
            ),
            prevent_user_existence_errors=True,
            id_token_validity=Duration.hours(1),
            access_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),
        )

        # Optionally create an initial operator user so the app is usable
        # immediately after deploy. Requires COGNITO_INITIAL_USER_EMAIL in config.
        if COGNITO_INITIAL_USER_EMAIL:
            cognito.CfnUserPoolUser(
                self, "MysqlUpgraderInitialUser",
                user_pool_id=user_pool.user_pool_id,
                username=COGNITO_INITIAL_USER_EMAIL,
                desired_delivery_mediums=["EMAIL"],
                user_attributes=[
                    cognito.CfnUserPoolUser.AttributeTypeProperty(
                        name="email", value=COGNITO_INITIAL_USER_EMAIL
                    ),
                    cognito.CfnUserPoolUser.AttributeTypeProperty(
                        name="email_verified", value="true"
                    ),
                ],
            )

        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self, "MysqlUpgraderAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name=f"mysql-upgrader-cognito-authorizer-{acct}",
        )

        # Keyword args applied to every method so all endpoints require a valid
        # Cognito JWT.
        auth_kwargs = dict(
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )

        # ── API Gateway ───────────────────────────────────────────────────────
        # Finding #2: CORS restricted to the known UI origin(s), methods limited
        # to POST/OPTIONS, and data_trace_enabled disabled so request/response
        # bodies (which contain DB credentials) are no longer written to logs.
        api = apigw.RestApi(
            self, "MysqlUpgraderApi",
            rest_api_name=f"mysql-upgrader-api-{acct}",
            description="API Gateway for MySQL Upgrade Accelerator",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=UI_ALLOWED_ORIGINS,
                allow_methods=["POST", "OPTIONS"],
                allow_headers=[
                    "Content-Type", "Authorization",
                    "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token",
                ],
                allow_credentials=True,
            ),
            deploy_options=apigw.StageOptions(
                stage_name="dev",
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=False,
            ),
        )

        def lambda_integration(fn: _lambda.Function) -> apigw.LambdaIntegration:
            return apigw.LambdaIntegration(fn, proxy=True, allow_test_invoke=True)

        api.root.add_resource("pre-checker").add_method("POST",      lambda_integration(prechecker_fn),    **auth_kwargs)
        api.root.add_resource("bg-deployment").add_method("POST",    lambda_integration(bg_deployment_fn), **auth_kwargs)
        api.root.add_resource("genai-summary").add_method("POST",    lambda_integration(genai_summary_fn), **auth_kwargs)
        api.root.add_resource("analyze-logs").add_method("POST",     lambda_integration(genai_summary_fn), **auth_kwargs)
        api.root.add_resource("task-logs").add_method("POST",        lambda_integration(task_logs_fn),     **auth_kwargs)
        api.root.add_resource("test-connection").add_method("POST",  lambda_integration(test_connection_fn), **auth_kwargs)
        api.root.add_resource("switchover").add_method("POST",       lambda_integration(switchover_fn),    **auth_kwargs)

        # ── Outputs ───────────────────────────────────────────────────────────
        self.api_url = api.url
        # Exposed for the UI stack to inject into the browser config.json so the
        # React app can authenticate against this user pool.
        self.user_pool_id = user_pool.user_pool_id
        self.user_pool_client_id = user_pool_client.user_pool_client_id

        CfnOutput(self, "ApiUrl",
            value=api.url,
            export_name=f"MysqlUpgraderApiUrl-{acct}",
        )
        CfnOutput(self, "CognitoUserPoolId",
            value=user_pool.user_pool_id,
            export_name=f"MysqlUpgraderUserPoolId-{acct}",
        )
        CfnOutput(self, "CognitoUserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            export_name=f"MysqlUpgraderUserPoolClientId-{acct}",
        )
        CfnOutput(self, "PrecheckerEndpoint",   value=f"{api.url}pre-checker")
        CfnOutput(self, "BgDeploymentEndpoint", value=f"{api.url}bg-deployment")
        CfnOutput(self, "GenAiSummaryEndpoint", value=f"{api.url}genai-summary")
        CfnOutput(self, "PrecheckerLambdaArn",
            value=prechecker_fn.function_arn,
            export_name=f"PrecheckerLambdaArn-{acct}",
        )
        CfnOutput(self, "BgDeploymentLambdaArn",
            value=bg_deployment_fn.function_arn,
            export_name=f"BgDeploymentLambdaArn-{acct}",
        )
        CfnOutput(self, "GenAiSummaryLambdaArn",
            value=genai_summary_fn.function_arn,
            export_name=f"GenAiSummaryLambdaArn-{acct}",
        )
