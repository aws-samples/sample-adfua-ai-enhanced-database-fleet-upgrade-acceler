from config import APP_BUCKET_NAME
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    Duration,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
    aws_codebuild as codebuild,
    aws_s3_assets as s3_assets,
    custom_resources as cr,
)
from constructs import Construct


class EcsStack(Stack):
    """
    Provisions shared ECS infrastructure for the MySQL Upgrade Accelerator.

    All named resources are suffixed with the AWS account number so the same
    stack can be deployed to multiple accounts without any name conflicts.

    Docker images are built in AWS via CodeBuild — no local Docker needed.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        acct = self.account
        app_bucket_name = APP_BUCKET_NAME            # already suffixed in config.py

        # ── ECR Repositories ─────────────────────────────────────────────────
        prechecker_repo = ecr.Repository(
            self, "PrecheckerRepo",
            repository_name=f"mysql-upgrader-prechecker-{acct}",
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                ecr.LifecycleRule(max_image_count=5, description="Keep last 5 images")
            ],
        )

        upgrader_repo = ecr.Repository(
            self, "UpgraderRepo",
            repository_name=f"mysql-upgrader-main-{acct}",
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                ecr.LifecycleRule(max_image_count=5, description="Keep last 5 images")
            ],
        )

        switchover_repo = ecr.Repository(
            self, "SwitchoverRepo",
            repository_name=f"mysql-upgrader-switchover-{acct}",
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                ecr.LifecycleRule(max_image_count=5, description="Keep last 5 images")
            ],
        )

        # ── S3 assets — CDK zips and uploads each docker/ folder ─────────────
        prechecker_source = s3_assets.Asset(
            self, "PrecheckerSource",
            path="docker/prechecker",
        )

        upgrader_source = s3_assets.Asset(
            self, "UpgraderSource",
            path="docker/upgrader",
        )

        switchover_source = s3_assets.Asset(
            self, "SwitchoverSource",
            path="docker/switchover",
        )

        # ── IAM role for CodeBuild ────────────────────────────────────────────
        codebuild_role = iam.Role(
            self, "CodeBuildRole",
            role_name=f"mysql-upgrader-codebuild-role-{acct}",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            inline_policies={
                "CodeBuildPolicy": iam.PolicyDocument(
                    statements=[
                        # GetAuthorizationToken must be on "*" (it authorizes the
                        # registry, not a repo). Push/pull actions are scoped to
                        # this app's three ECR repositories only.
                        iam.PolicyStatement(
                            sid="EcrAuth",
                            actions=["ecr:GetAuthorizationToken"],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            sid="EcrPushPull",
                            actions=[
                                "ecr:BatchCheckLayerAvailability",
                                "ecr:GetDownloadUrlForLayer",
                                "ecr:BatchGetImage",
                                "ecr:InitiateLayerUpload",
                                "ecr:UploadLayerPart",
                                "ecr:CompleteLayerUpload",
                                "ecr:PutImage",
                            ],
                            resources=[
                                prechecker_repo.repository_arn,
                                upgrader_repo.repository_arn,
                                switchover_repo.repository_arn,
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="ReadBuildSources",
                            actions=["s3:GetObject", "s3:GetObjectVersion"],
                            resources=[
                                f"{prechecker_source.bucket.bucket_arn}/*",
                                f"{upgrader_source.bucket.bucket_arn}/*",
                                f"{switchover_source.bucket.bucket_arn}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="CloudWatchLogs",
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{acct}:log-group:/codebuild/mysql-upgrader-*:*",
                            ],
                        ),
                    ]
                )
            },
        )

        # ── CodeBuild project factory ─────────────────────────────────────────
        def make_build_project(name: str, repo: ecr.Repository, source_asset: s3_assets.Asset) -> codebuild.Project:
            return codebuild.Project(
                self, f"{name}BuildProject",
                project_name=f"mysql-upgrader-build-{name.lower()}-{acct}",
                role=codebuild_role,
                source=codebuild.Source.s3(
                    bucket=source_asset.bucket,
                    path=source_asset.s3_object_key,
                ),
                environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                    privileged=True,
                    compute_type=codebuild.ComputeType.MEDIUM,
                ),
                environment_variables={
                    "AWS_ACCOUNT_ID":    codebuild.BuildEnvironmentVariable(value=self.account),
                    "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                    "ECR_REPO_URI":      codebuild.BuildEnvironmentVariable(value=repo.repository_uri),
                },
                build_spec=codebuild.BuildSpec.from_object({
                    "version": "0.2",
                    "phases": {
                        "pre_build": {
                            "commands": [
                                "aws ecr get-login-password --region $AWS_DEFAULT_REGION "
                                "| docker login --username AWS --password-stdin "
                                "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com",
                            ]
                        },
                        "build": {
                            "commands": [
                                "docker build --platform linux/amd64 -t $ECR_REPO_URI:latest .",
                            ]
                        },
                        "post_build": {
                            "commands": [
                                "docker push $ECR_REPO_URI:latest",
                                "echo Build completed successfully",
                            ]
                        },
                    },
                }),
                timeout=Duration.minutes(30),
                logging=codebuild.LoggingOptions(
                    cloud_watch=codebuild.CloudWatchLoggingOptions(
                        log_group=logs.LogGroup(
                            self, f"{name}BuildLogs",
                            log_group_name=f"/codebuild/mysql-upgrader-{name.lower()}-{acct}",
                            retention=logs.RetentionDays.ONE_WEEK,
                            removal_policy=RemovalPolicy.DESTROY,
                        )
                    )
                ),
            )

        prechecker_build  = make_build_project("Prechecker",  prechecker_repo,  prechecker_source)
        upgrader_build    = make_build_project("Upgrader",    upgrader_repo,    upgrader_source)
        switchover_build  = make_build_project("Switchover",  switchover_repo,  switchover_source)

        # ── Custom resource — triggers CodeBuild on every cdk deploy ─────────
        trigger_role = iam.Role(
            self, "BuildTriggerRole",
            role_name=f"mysql-upgrader-build-trigger-role-{acct}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            inline_policies={
                "TriggerPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["codebuild:StartBuild", "codebuild:BatchGetBuilds"],
                            resources=[
                                prechecker_build.project_arn,
                                upgrader_build.project_arn,
                                switchover_build.project_arn,
                            ],
                        )
                    ]
                )
            },
        )

        def make_build_trigger(name: str, project: codebuild.Project, source_asset: s3_assets.Asset):
            cr.AwsCustomResource(
                self, f"{name}BuildTrigger",
                role=trigger_role,
                on_create=cr.AwsSdkCall(
                    service="CodeBuild",
                    action="startBuild",
                    parameters={"projectName": project.project_name},
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"{project.project_name}-{source_asset.asset_hash}"
                    ),
                ),
                on_update=cr.AwsSdkCall(
                    service="CodeBuild",
                    action="startBuild",
                    parameters={"projectName": project.project_name},
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"{project.project_name}-{source_asset.asset_hash}"
                    ),
                ),
                timeout=Duration.minutes(15),
            )

        make_build_trigger("Prechecker",  prechecker_build,  prechecker_source)
        make_build_trigger("Upgrader",    upgrader_build,    upgrader_source)
        make_build_trigger("Switchover",  switchover_build,  switchover_source)

        # ── IAM: ECS Task Execution Role ──────────────────────────────────────
        execution_role = iam.Role(
            self, "EcsTaskExecutionRole",
            role_name=f"mysql-upgrader-ecs-execution-role-{acct}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        # ── IAM: ECS Task Role ────────────────────────────────────────────────
        task_role = iam.Role(
            self, "EcsTaskRole",
            role_name=f"mysql-upgrader-ecs-task-role-{acct}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "MysqlUpgraderTaskPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="S3Access",
                            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                            resources=[
                                f"arn:aws:s3:::{app_bucket_name}",
                                f"arn:aws:s3:::{app_bucket_name}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="SecretsManagerRead",
                            actions=["secretsmanager:GetSecretValue"],
                            resources=[
                                f"arn:aws:secretsmanager:{self.region}:{acct}:secret:mysql-upgrader/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="RDSDescribe",
                            # Read-only describe APIs do not all support
                            # resource-level scoping; separated from mutations.
                            actions=[
                                "rds:DescribeDBInstances",
                                "rds:DescribeDBClusters",
                                "rds:DescribeDBSnapshots",
                                "rds:DescribeDBClusterSnapshots",
                                "rds:DescribeBlueGreenDeployments",
                                "rds:DescribeDBParameterGroups",
                            ],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            sid="RDSMutate",
                            actions=[
                                "rds:CreateDBSnapshot",
                                "rds:CreateDBClusterSnapshot",
                                "rds:CreateBlueGreenDeployment",
                                "rds:SwitchoverBlueGreenDeployment",
                                "rds:DeleteBlueGreenDeployment",
                                "rds:CreateDBParameterGroup",
                                "rds:CreateDBClusterParameterGroup",
                                "rds:ModifyDBParameterGroup",
                                "rds:ModifyDBClusterParameterGroup",
                                "rds:ModifyDBInstance",
                                "rds:ModifyDBCluster",
                                "rds:CreateDBInstanceReadReplica",
                                "rds:PromoteReadReplica",
                                "rds:AddTagsToResource",
                            ],
                            resources=[
                                f"arn:aws:rds:{self.region}:{acct}:db:*",
                                f"arn:aws:rds:{self.region}:{acct}:cluster:*",
                                f"arn:aws:rds:{self.region}:{acct}:snapshot:*",
                                f"arn:aws:rds:{self.region}:{acct}:cluster-snapshot:*",
                                f"arn:aws:rds:{self.region}:{acct}:pg:*",
                                f"arn:aws:rds:{self.region}:{acct}:cluster-pg:*",
                                f"arn:aws:rds:{self.region}:{acct}:deployment:*",
                                f"arn:aws:rds:{self.region}:{acct}:blue-green-deployment:*",
                                f"arn:aws:rds:{self.region}:{acct}:ri:*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="CloudWatchLogs",
                            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=[
                                f"arn:aws:logs:{self.region}:{acct}:log-group:/ecs/mysql-*:*",
                            ],
                        ),
                    ]
                )
            },
        )

        # ── ECS Cluster ───────────────────────────────────────────────────────
        cluster = ecs.Cluster(
            self, "MysqlUpgradeCluster",
            cluster_name=f"mysql-upgrade-cluster-{acct}",
        )

        # ── CloudWatch Log Groups ─────────────────────────────────────────────
        prechecker_log_group = logs.LogGroup(
            self, "PrecheckerLogGroup",
            log_group_name=f"/ecs/mysql-prechecker-{acct}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        upgrader_log_group = logs.LogGroup(
            self, "UpgraderLogGroup",
            log_group_name=f"/ecs/mysql-upgrader-{acct}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        switchover_log_group = logs.LogGroup(
            self, "SwitchoverLogGroup",
            log_group_name=f"/ecs/mysql-switchover-{acct}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── ECS Task Definition: Prechecker ───────────────────────────────────
        prechecker_task = ecs.FargateTaskDefinition(
            self, "PrecheckerTaskDef",
            family=f"mysql-prechecker-{acct}",
            cpu=1024,
            memory_limit_mib=2048,
            execution_role=execution_role,
            task_role=task_role,
        )
        prechecker_task.add_container(
            "PrecheckerContainer",
            container_name=f"mysql-prechecker-{acct}",
            image=ecs.ContainerImage.from_ecr_repository(prechecker_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ecs",
                log_group=prechecker_log_group,
            ),
            essential=True,
        )

        # ── ECS Task Definition: Upgrader ─────────────────────────────────────
        upgrader_task = ecs.FargateTaskDefinition(
            self, "UpgraderTaskDef",
            family=f"mysql-upgrader-{acct}",
            cpu=1024,
            memory_limit_mib=2048,
            execution_role=execution_role,
            task_role=task_role,
        )
        upgrader_task.add_container(
            "UpgraderContainer",
            container_name=f"mysql-upgrader-{acct}",
            image=ecs.ContainerImage.from_ecr_repository(upgrader_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ecs",
                log_group=upgrader_log_group,
            ),
            essential=True,
        )

        # ── ECS Task Definition: Switchover ───────────────────────────────────
        switchover_task = ecs.FargateTaskDefinition(
            self, "SwitchoverTaskDef",
            family=f"mysql-switchover-{acct}",
            cpu=512,
            memory_limit_mib=1024,
            execution_role=execution_role,
            task_role=task_role,
        )
        switchover_task.add_container(
            "SwitchoverContainer",
            container_name=f"mysql-switchover-{acct}",
            image=ecs.ContainerImage.from_ecr_repository(switchover_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ecs",
                log_group=switchover_log_group,
            ),
            essential=True,
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "ClusterName",
            value=cluster.cluster_name,
            export_name=f"MysqlUpgradeClusterName-{acct}",
        )
        CfnOutput(self, "PrecheckerTaskDefArn",
            value=prechecker_task.task_definition_arn,
            export_name=f"PrecheckerTaskDefArn-{acct}",
        )
        CfnOutput(self, "UpgraderTaskDefArn",
            value=upgrader_task.task_definition_arn,
            export_name=f"UpgraderTaskDefArn-{acct}",
        )
        CfnOutput(self, "PrecheckerRepoUri",
            value=prechecker_repo.repository_uri,
            export_name=f"PrecheckerRepoUri-{acct}",
        )
        CfnOutput(self, "UpgraderRepoUri",
            value=upgrader_repo.repository_uri,
            export_name=f"UpgraderRepoUri-{acct}",
        )
        CfnOutput(self, "SwitchoverTaskDefArn",
            value=switchover_task.task_definition_arn,
            export_name=f"SwitchoverTaskDefArn-{acct}",
        )
        CfnOutput(self, "SwitchoverRepoUri",
            value=switchover_repo.repository_uri,
            export_name=f"SwitchoverRepoUri-{acct}",
        )
