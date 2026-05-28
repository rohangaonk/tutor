# Tutor Infra

This directory contains the AWS CDK infrastructure code for Tutor.

## Usage

- All CDK commands should use the `tutor-deploy` profile:
  
  ```sh
  cdk synth --profile tutor-deploy
  cdk deploy --profile tutor-deploy
  cdk bootstrap --profile tutor-deploy
  ```

- The stacks will provision AWS resources for the backend, worker, and data layers.

## Prerequisites

- AWS CLI configured with the `tutor-deploy` profile
- Node.js and npm installed
- AWS CDK v2 installed globally (`npm install -g aws-cdk`)

## Next Steps

1. Run `npx cdk init app --language typescript` in this directory to scaffold the CDK project.
2. Add stacks for VPC, RDS, S3, SQS, ElastiCache, and ECS Fargate.
3. Use the `tutor-deploy` profile for all deployments.

---

See the main roadmap for deployment phases and stack responsibilities.
