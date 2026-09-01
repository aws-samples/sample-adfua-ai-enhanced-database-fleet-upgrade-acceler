#!/usr/bin/env python3
import aws_cdk as cdk
from config import AWS_ACCOUNT, AWS_REGION
from stacks.ecs_stack import EcsStack
from stacks.api_stack import ApiStack
from stacks.s3_ui_stack import S3UiStack

app = cdk.App()

env = cdk.Environment(account=AWS_ACCOUNT, region=AWS_REGION)

ecs_stack = EcsStack(app, "MysqlUpgraderEcsStack", env=env)

api_stack = ApiStack(app, "MysqlUpgraderApiStack", env=env)
api_stack.add_dependency(ecs_stack)

ui_stack = S3UiStack(app, "MysqlUpgraderUiStack",
    api_url=api_stack.api_url,
    user_pool_id=api_stack.user_pool_id,
    user_pool_client_id=api_stack.user_pool_client_id,
    env=env,
)
ui_stack.add_dependency(api_stack)

app.synth()
