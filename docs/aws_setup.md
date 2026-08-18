# AWS Setup Guide — NASDAQ Day Trading Predictor

> Complete step-by-step instructions for setting up all AWS resources required for Phase 2 cloud deployment.
>
> **Estimated time: 30–40 minutes**
>
> **Estimated monthly cost: ~$1–2/month**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [AWS Account Setup](#2-aws-account-setup)
3. [AWS CLI Installation & Configuration](#3-aws-cli-installation--configuration)
4. [GitHub Repository Setup](#4-github-repository-setup)
5. [Create S3 Bucket](#5-create-s3-bucket)
6. [Create ECR Repository](#6-create-ecr-repository)
7. [Create IAM Roles & Policies](#7-create-iam-roles--policies)
8. [Create ECS Cluster](#8-create-ecs-cluster)
9. [Create CloudWatch Log Group](#9-create-cloudwatch-log-group)
10. [Create Glue Database](#10-create-glue-database)
11. [Create Athena Workgroup](#11-create-athena-workgroup)
12. [Create EventBridge Rule](#12-create-eventbridge-rule)
13. [Configure GitHub Secrets](#13-configure-github-secrets)
14. [Configure Local .env File](#14-configure-local-env-file)
15. [Default VPC Verification](#15-default-vpc-verification)
16. [Verification Checklist](#16-verification-checklist)

---

## 1. Prerequisites

Before starting, ensure you have:

- [ ] A modern web browser (for AWS Console)
- [ ] A terminal on macOS
- [ ] Docker Desktop installed and running
- [ ] Git installed
- [ ] Python 3.10+ installed
- [ ] A credit/debit card (for AWS account — free tier eligible)

---

## 2. AWS Account Setup

**Skip this section if you already have an AWS account.**

1. Go to [https://aws.amazon.com/free/](https://aws.amazon.com/free/)
2. Click **"Create a Free Account"**
3. Enter your email, choose an account name (e.g., `zoya-personal`)
4. Verify your email
5. Enter payment information (you won't be charged for free tier usage)
6. Choose the **Basic (Free)** support plan
7. Complete identity verification (phone call or SMS)
8. Wait for account activation (usually 1–5 minutes)

### Find Your Account ID

1. Log in to the [AWS Console](https://console.aws.amazon.com/)
2. Click your account name in the top-right corner
3. Your **12-digit Account ID** is displayed (e.g., `123456789012`)
4. **Write this down** — you'll need it later

```
📝 YOUR AWS ACCOUNT ID: 5030-2694-2580

```

---

## 3. AWS CLI Installation & Configuration

### Install AWS CLI v2

Open Terminal and run:

```bash
# Download the installer
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"

# Install
sudo installer -pkg AWSCLIV2.pkg -target /

# Verify
aws --version
# Should show: aws-cli/2.x.x ...

# Clean up
rm AWSCLIV2.pkg
```

### Create an IAM User for CLI Access

1. Go to the [IAM Console](https://console.aws.amazon.com/iam/)
2. Click **Users** in the left sidebar
3. Click **Create user**
4. User name: `stock-predictor-admin`
5. Check **"Provide user access to the AWS Management Console"** — select **"I want to create an IAM user"**
6. Set a console password or auto-generate one
7. Click **Next**
8. On the **Set permissions** page:
   - Select **"Attach policies directly"**
   - Search for and check these policies:
     - `AmazonS3FullAccess`
     - `AmazonEC2ContainerRegistryFullAccess`
     - `AmazonECS_FullAccess`
     - `AWSGlueServiceRole`
     - `AmazonAthenaFullAccess`
     - `CloudWatchLogsFullAccess`
     - `AmazonEventBridgeFullAccess`
     - `IAMReadOnlyAccess`
9. Click **Next**, then **Create user**

### Create Access Keys

1. Click the user you just created (`stock-predictor-admin`)
2. Go to **Security credentials** tab
3. Scroll to **Access keys**
4. Click **Create access key**
5. Select **"Command Line Interface (CLI)"**
6. Check the acknowledgment box
7. Click **Next**, then **Create access key**
8. **IMPORTANT**: Copy both values now — the Secret Key is shown only once!

```
📝 YOUR ACCESS KEY ID:     REPLACE_WITH_YOUR_KEY_ID
📝 YOUR SECRET ACCESS KEY: REPLACE_WITH_YOUR_SECRET_KEY
```

> ⚠️ **Never commit these keys to Git!** They go in your `.env` file (which is `.gitignore`d) and GitHub Secrets only.

### Configure AWS CLI

```bash
aws configure
```

Enter the following when prompted:

```
AWS Access Key ID [None]: <your-access-key-id>
AWS Secret Access Key [None]: <your-secret-access-key>
Default region name [None]: us-east-1
Default output format [None]: json
```

### Verify CLI Works

```bash
aws sts get-caller-identity
```

Expected output:

```json
{
    "UserId": "AIDA...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/stock-predictor-admin"
}
```

---

## 4. GitHub Repository Setup

### Create a GitHub Repository

1. Go to [https://github.com/new](https://github.com/new)
2. Repository name: `stock-market-predictor` (or your preferred name)
3. Description: `End-to-end NASDAQ day trading prediction pipeline with AWS deployment`
4. Set to **Public** (recommended for portfolio) or **Private**
5. Do NOT initialize with README (we already have one)
6. Click **Create repository**

### Push Your Code

```bash
cd "/Users/ZoyaOsmani/.gemini/antigravity/scratch/Stock market predictor"

git init
git add .
git commit -m "Phase 1: Local MVP - complete end-to-end pipeline"
git branch -M main
git remote add origin https://github.com/<your-username>/stock-market-predictor.git
git push -u origin main
```

```
📝 YOUR GITHUB REPO URL: https://github.com/ShariqO/stock-market-predictor
```

---

## 5. Create S3 Bucket

1. Go to the [S3 Console](https://s3.console.aws.amazon.com/s3/)
2. Click **Create bucket**
3. Configure:

| Setting | Value |
|---------|-------|
| Bucket name | `stock-predictor-lake-<your-initials-or-id>` (must be globally unique) |
| AWS Region | **US East (N. Virginia) us-east-1** |
| Object Ownership | ACLs disabled (recommended) |
| Block Public Access | **Block all** (keep all 4 boxes checked) |
| Bucket Versioning | Disable |
| Default encryption | SSE-S3 (default) |

4. Click **Create bucket**

```
📝 YOUR S3 BUCKET NAME: stock-predictor-lake-YOUR_ACCOUNT_ID-us-east-1
```

### Verify

```bash
aws s3 ls s3://<your-bucket-name>/
# Should return empty (no error)
```

---

## 6. Create ECR Repository

1. Go to the [ECR Console](https://console.aws.amazon.com/ecr/)
2. Make sure you're in **us-east-1** (top-right dropdown)
3. Click **Get Started** or **Create repository**
4. Configure:

| Setting | Value |
|---------|-------|
| Visibility | Private |
| Repository name | `stock-predictor` |
| Tag immutability | Disabled |
| Image scan on push | Enabled |

5. Click **Create repository**
6. Note the **URI** shown (e.g., `123456789012.dkr.ecr.us-east-1.amazonaws.com/stock-predictor`)

```
📝 YOUR ECR REPOSITORY URI: 123456789012.dkr.ecr.us-east-1.amazonaws.com/stock-predictor
📝 YOUR ECR REGISTRY (without /stock-predictor): 123456789012.dkr.ecr.us-east-1.amazonaws.com
```

### Verify

```bash
aws ecr describe-repositories --repository-names stock-predictor --region us-east-1
```

---

## 7. Create IAM Roles & Policies

You need **two** IAM roles for ECS Fargate:

### 7a. ECS Task Execution Role

This role allows ECS to pull Docker images from ECR and write logs to CloudWatch.

1. Go to the [IAM Console → Roles](https://console.aws.amazon.com/iam/home#/roles)
2. Click **Create role**
3. **Trusted entity type**: AWS service
4. **Use case**: Select **Elastic Container Service** → **Elastic Container Service Task**
5. Click **Next**
6. Search for and attach these policies:
   - `AmazonECSTaskExecutionRolePolicy`
7. Click **Next**
8. **Role name**: `stock-predictor-ecs-execution-role`
9. **Description**: `Allows ECS tasks to pull images from ECR and push logs to CloudWatch`
10. Click **Create role**
11. Note the **Role ARN** (e.g., `arn:aws:iam::123456789012:role/stock-predictor-ecs-execution-role`)

```
📝 EXECUTION ROLE ARN: arn:aws:iam::123456789012:role/stock-predictor-ecs-execution-role
```

### 7b. ECS Task Role

This role gives your pipeline code permission to access S3, Glue, and Athena.

1. Click **Create role** again
2. **Trusted entity type**: AWS service
3. **Use case**: Select **Elastic Container Service** → **Elastic Container Service Task**
4. Click **Next**
5. Search for and attach these policies:
   - `AmazonS3FullAccess`
   - `AWSGlueServiceRole`
   - `AmazonAthenaFullAccess`
   - `CloudWatchLogsFullAccess`
6. Click **Next**
7. **Role name**: `stock-predictor-task-role`
8. **Description**: `Allows the stock predictor pipeline to access S3, Glue, Athena, and CloudWatch`
9. Click **Create role**
10. Note the **Role ARN**

```
📝 TASK ROLE ARN: arn:aws:iam::123456789012:role/stock-predictor-task-role
```

### 7c. CI/CD IAM User (for GitHub Actions)

This user allows GitHub Actions to push Docker images and update ECS tasks.

1. Go to **IAM → Users**
2. Click **Create user**
3. User name: `stock-predictor-cicd`
4. Do NOT check console access (this is a programmatic-only user)
5. Click **Next**
6. Select **"Attach policies directly"**
7. Attach these policies:
   - `AmazonEC2ContainerRegistryFullAccess`
   - `AmazonECS_FullAccess`
8. Click **Next**, then **Create user**
9. Click the user → **Security credentials** → **Create access key**
10. Select **"Third-party service"** → check acknowledgment → **Next** → **Create**
11. Copy both keys:

```
📝 CI/CD ACCESS KEY ID:     REPLACE_WITH_YOUR_CICD_KEY_ID
📝 CI/CD SECRET ACCESS KEY: REPLACE_WITH_YOUR_CICD_SECRET_KEY
```

---

## 8. Create ECS Cluster

1. Go to the [ECS Console](https://console.aws.amazon.com/ecs/)
2. Make sure you're in **us-east-1**
3. Click **Create cluster**
4. Configure:

| Setting | Value |
|---------|-------|
| Cluster name | `stock-predictor-cluster` |
| Infrastructure | **AWS Fargate (serverless)** only — uncheck EC2 instances |

5. Leave all other settings as default
6. Click **Create**

### Verify

```bash
aws ecs list-clusters --region us-east-1
# Should show arn:aws:ecs:us-east-1:<account-id>:cluster/stock-predictor-cluster
```

---

## 9. Create CloudWatch Log Group

1. Go to the [CloudWatch Console → Log groups](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups)
2. Click **Create log group**
3. Configure:

| Setting | Value |
|---------|-------|
| Log group name | `/ecs/stock-predictor` |
| Retention | 30 days (saves cost) |

4. Click **Create**

### Verify

```bash
aws logs describe-log-groups --log-group-name-prefix /ecs/stock-predictor --region us-east-1
```

---

## 10. Create Glue Database

1. Go to the [AWS Glue Console → Databases](https://console.aws.amazon.com/glue/home#/v2/data-catalog/databases)
2. Click **Add database**
3. Configure:

| Setting | Value |
|---------|-------|
| Database name | `stock_predictor` |
| Location | `s3://<your-bucket-name>/` |
| Description | `NASDAQ Day Trading Predictor - data lake catalog` |

4. Click **Create database**

> **Note**: The actual tables will be created programmatically by running `python aws/glue_tables.py` after we deploy the code. You only need to create the database shell here.

### Verify

```bash
aws glue get-database --name stock_predictor --region us-east-1
```

---

## 11. Create Athena Workgroup

### 11a. Create a Results Bucket (or folder)

Athena needs a location to store query results:

1. Go to the [S3 Console](https://s3.console.aws.amazon.com/s3/)
2. Open your existing bucket (`stock-predictor-lake-<id>`)
3. Click **Create folder**
4. Folder name: `athena-results`
5. Click **Create folder**

### 11b. Create Athena Workgroup

1. Go to the [Athena Console](https://console.aws.amazon.com/athena/)
2. Click **Workgroups** in the left sidebar
3. Click **Create workgroup**
4. Configure:

| Setting | Value |
|---------|-------|
| Workgroup name | `stock-predictor-workgroup` |
| Analytics engine | Athena SQL |
| Query result location | `s3://<your-bucket-name>/athena-results/` |
| Encrypt query results | Unchecked (optional) |

5. Click **Create workgroup**

### 11c. Set as Default

1. In the Athena query editor, click the **Workgroup** dropdown (top-right area)
2. Select `stock-predictor-workgroup`

---

## 12. Create EventBridge Rule

This schedules the pipeline to run at **9:00 AM Eastern, weekdays only**.

> **Note**: Create this AFTER the ECS task definition has been registered (we'll do that during deployment). For now, just understand what you'll create.

1. Go to the [EventBridge Console → Rules](https://console.aws.amazon.com/events/)
2. Click **Create rule**
3. Configure:

| Setting | Value |
|---------|-------|
| Name | `stock-predictor-weekday-9am` |
| Description | `Run stock predictor pipeline weekdays at 9 AM ET` |
| Event bus | default |
| Rule type | Schedule |

4. **Schedule pattern**: `cron(0 13 ? * MON-FRI *)`
   - (9 AM ET = 1 PM UTC during EDT, 2 PM UTC during EST)
5. **Target**: Select **ECS task**
   - Cluster: `stock-predictor-cluster`
   - Task definition: `stock-predictor` (latest revision)
   - Launch type: FARGATE
   - Platform version: LATEST
   - Subnets: Select your default VPC subnets (see Section 15)
   - Security groups: Use default security group
   - Auto-assign public IP: ENABLED
6. **Execution role**: Create a new role or select one with EventBridge-to-ECS permissions
7. Click **Create rule**

> ⏸️ **We'll do this step together during deployment.** Skip for now.

---

## 13. Configure GitHub Secrets

Once you have all the values above, add them to your GitHub repository:

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** for each:

| Secret Name | Value |
|-------------|-------|
| `AWS_ACCESS_KEY_ID` | CI/CD user access key from Step 7c |
| `AWS_SECRET_ACCESS_KEY` | CI/CD user secret key from Step 7c |
| `AWS_ACCOUNT_ID` | Your 12-digit account ID |
| `AWS_REGION` | `us-east-1` |
| `ECR_REPOSITORY` | `stock-predictor` |
| `S3_BUCKET` | Your S3 bucket name from Step 5 |
| `ECS_CLUSTER` | `stock-predictor-cluster` |
| `ECS_TASK_DEFINITION` | `stock-predictor` |
| `EXECUTION_ROLE_ARN` | From Step 7a |
| `TASK_ROLE_ARN` | From Step 7b |

---

## 14. Configure Local .env File

Update your local `.env` file with your AWS values:

```bash
# ── Mode ──────────────────────────────────────────────────
# Set to 'aws' when ready to deploy to cloud
MODE=local

# ── AWS Configuration ────────────────────────────────────
AWS_ACCESS_KEY_ID=<your-admin-access-key-from-step-3>
AWS_SECRET_ACCESS_KEY=<your-admin-secret-key-from-step-3>
AWS_DEFAULT_REGION=us-east-1
AWS_ACCOUNT_ID=<your-12-digit-account-id>

# ── S3 ───────────────────────────────────────────────────
S3_BUCKET=<your-bucket-name-from-step-5>

# ── ECR ──────────────────────────────────────────────────
ECR_REGISTRY=<account-id>.dkr.ecr.us-east-1.amazonaws.com
ECR_REPOSITORY=stock-predictor

# ── ECS ──────────────────────────────────────────────────
ECS_CLUSTER=stock-predictor-cluster
ECS_EXECUTION_ROLE_ARN=arn:aws:iam::<account-id>:role/stock-predictor-ecs-execution-role
ECS_TASK_ROLE_ARN=arn:aws:iam::<account-id>:role/stock-predictor-task-role

# ── Glue ─────────────────────────────────────────────────
GLUE_DATABASE=stock_predictor

# ── Logging ──────────────────────────────────────────────
LOG_LEVEL=INFO
```

> ⚠️ **Do NOT commit the `.env` file!** It is in `.gitignore`.

---

## 15. Default VPC Verification

The ECS Fargate tasks use your **default VPC** with public subnets and a public IP. Verify it exists:

```bash
# Find your default VPC
aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --region us-east-1 \
  --query "Vpcs[0].VpcId" --output text
```

```
📝 YOUR DEFAULT VPC ID: vpc-0359052038bb90aa7
```

```bash
# Find subnets in the default VPC
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-xxxxxxxxx" \
  --region us-east-1 \
  --query "Subnets[*].[SubnetId,AvailabilityZone]" \
  --output table
```

```
📝 YOUR SUBNET IDs (pick 2):
  Subnet 1: subnet-xxxxxxxxx1
  Subnet 2: subnet-xxxxxxxxx2
```

```bash
# Find the default security group
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=vpc-xxxxxxxxx" "Name=group-name,Values=default" \
  --region us-east-1 \
  --query "SecurityGroups[0].GroupId" --output text
```

```
📝 YOUR DEFAULT SECURITY GROUP ID: sg-xxxxxxxxx
```

> The default security group allows all outbound traffic (needed for yfinance API calls). No inbound rules are needed since the pipeline doesn't serve traffic.

---

## 16. Verification Checklist

After completing all steps above, verify you have ALL of these values filled in:

```
CHECKLIST — ALL VALUES REQUIRED BEFORE DEPLOYMENT
═══════════════════════════════════════════════════

AWS Account:
  [ ] Account ID:           123456789012
  [ ] Region:               us-east-1

AWS CLI:
  [ ] aws --version works:  Yes
  [ ] aws sts get-caller-identity works: Yes

S3:
  [ ] Bucket name:          stock-predictor-lake-YOUR_ACCOUNT_ID-us-east-1

ECR:
  [ ] Repository URI:       123456789012.dkr.ecr.us-east-1.amazonaws.com/stock-predictor
  [ ] Registry URL:         123456789012.dkr.ecr.us-east-1.amazonaws.com

IAM Roles:
  [ ] Execution Role ARN:   arn:aws:iam::123456789012:role/stock-predictor-ecs-execution-role
  [ ] Task Role ARN:        arn:aws:iam::123456789012:role/stock-predictor-task-role

IAM CI/CD User:
  [ ] Access Key ID:        REPLACE_WITH_YOUR_CICD_KEY_ID
  [ ] Secret Access Key:    REPLACE_WITH_YOUR_CICD_SECRET_KEY

ECS:
  [ ] Cluster name:         stock-predictor-cluster
  [ ] Cluster created:      Yes

CloudWatch:
  [ ] Log group:            /ecs/stock-predictor
  [ ] Log group created:    Yes

Glue:
  [ ] Database name:        stock_predictor
  [ ] Database created:     Yes

Athena:
  [ ] Workgroup:            stock-predictor-workgroup
  [ ] Results location:     s3://stock-predictor-lake-YOUR_ACCOUNT_ID-us-east-1/athena-results/
  [ ] Workgroup created:    Yes

VPC/Networking:
  [ ] Default VPC ID:       vpc-xxxxxxxxx
  [ ] Subnet 1:             subnet-xxxxxxxxx1
  [ ] Subnet 2:             subnet-xxxxxxxxx2
  [ ] Security Group:       sg-xxxxxxxxx

GitHub:
  [ ] Repository URL:       https://github.com/YOUR_GITHUB_USERNAME/stock-market-predictor
  [ ] All 10 secrets added: Yes

Local .env:
  [ ] Updated with all AWS values: Yes
```

---

## Resource Summary

| Resource | Name | Service | Cost |
|----------|------|---------|------|
| S3 Bucket | `stock-predictor-lake-<id>` | S3 | ~$0.05/mo |
| ECR Repo | `stock-predictor` | ECR | ~$0.50/mo |
| ECS Cluster | `stock-predictor-cluster` | ECS | $0 (pay per task) |
| Fargate Tasks | On-demand | ECS Fargate | ~$0.50/mo |
| Log Group | `/ecs/stock-predictor` | CloudWatch | Free tier |
| Glue DB | `stock_predictor` | Glue | ~$0.01/mo |
| Athena | `stock-predictor-workgroup` | Athena | ~$0.005/query |
| EventBridge | `stock-predictor-weekday-9am` | EventBridge | Free tier |
| IAM Roles | 2 roles + 2 users | IAM | Free |
| **Total** | | | **~$1–2/mo** |

---

## Troubleshooting

### "Access Denied" errors
- Verify the IAM user/role has the correct policies attached
- Check that the S3 bucket name in `.env` matches exactly (case-sensitive)
- Run `aws sts get-caller-identity` to confirm which user/role you're using

### Default VPC doesn't exist
If your account is very old or the default VPC was deleted:
```bash
aws ec2 create-default-vpc --region us-east-1
```

### ECR login fails
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
```

### ECS task fails to start
- Check CloudWatch Logs at `/ecs/stock-predictor`
- Ensure the security group allows outbound traffic (port 443 for HTTPS)
- Verify the task has **"Assign public IP: ENABLED"** (needed without NAT Gateway)
