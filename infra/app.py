#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.vpc_stack import VpcStack
from stacks.data_stack import DataStack
from stacks.app_stack import AppStack

app = cdk.App()

stage: str = app.node.try_get_context("stage") or "staging"
account: str = app.node.try_get_context("account") or os.environ.get("CDK_DEFAULT_ACCOUNT", "")
region: str = app.node.try_get_context("region") or os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

env = cdk.Environment(account=account, region=region)

vpc_stack = VpcStack(app, f"TutorVpc-{stage}", stage=stage, env=env)

data_stack = DataStack(
    app,
    f"TutorData-{stage}",
    stage=stage,
    env=env,
)

app_stack = AppStack(
    app,
    f"TutorApp-{stage}",
    stage=stage,
    vpc=vpc_stack.vpc,
    data_stack=data_stack,
    env=env,
)
app_stack.add_dependency(data_stack)

app.synth()
