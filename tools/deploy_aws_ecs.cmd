@echo off
rem Deploy Fraud Hunter to AWS with ECS Express Mode (App Runner is closed to new accounts).
rem Usage:  tools\deploy_aws_ecs.cmd YOUR_API_KEY https://your-frontend-origin [region]
rem Needs:  Docker Desktop running, AWS CLI set up (set AWS_PROFILE=...).
setlocal
set KEY=%~1
set ORG=%~2
set REG=%~3
if "%REG%"=="" set REG=ap-south-1
if "%KEY%"=="" (echo Usage: tools\deploy_aws_ecs.cmd API_KEY ORIGIN [region] & exit /b 1)
if "%ORG%"=="" set ORG=*

for /f %%a in ('aws sts get-caller-identity --query Account --output text') do set ACC=%%a
if "%ACC%"=="" (echo AWS login failed & exit /b 1)
set HOST=%ACC%.dkr.ecr.%REG%.amazonaws.com
set IMG=%HOST%/fraud-hunter:latest
echo Account %ACC%, region %REG%

echo [1/4] Image in ECR (skipped if already pushed)
aws ecr create-repository --repository-name fraud-hunter --region %REG% >nul 2>&1
aws ecr describe-images --repository-name fraud-hunter --image-ids imageTag=latest --region %REG% >nul 2>&1
if errorlevel 1 (
  aws ecr get-login-password --region %REG% | docker login --username AWS --password-stdin %HOST%
  docker build -t fraud-hunter . || exit /b 1
  docker tag fraud-hunter %IMG% || exit /b 1
  docker push %IMG% || exit /b 1
) else (echo image already there)

echo [2/4] Roles
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com >nul 2>&1
aws iam create-role --role-name fhTaskExec --assume-role-policy-document file://tools/aws/trust_task.json >nul 2>&1
aws iam attach-role-policy --role-name fhTaskExec --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam create-role --role-name fhInfra --assume-role-policy-document file://tools/aws/trust_infra.json >nul 2>&1
aws iam attach-role-policy --role-name fhInfra --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
set EXE=arn:aws:iam::%ACC%:role/fhTaskExec
set INF=arn:aws:iam::%ACC%:role/fhInfra
timeout /t 30 /nobreak >nul

echo [3/4] Create the service (one task only: the feature store lives in memory)
powershell -NoProfile -Command "(Get-Content tools\aws\express.json -Raw).Replace('__EXE__','%EXE%').Replace('__INF__','%INF%').Replace('__IMG__','%IMG%').Replace('__KEY__','%KEY%').Replace('__ORG__','%ORG%') | Set-Content fh_exp.json -Encoding ascii"
aws ecs create-express-gateway-service --cli-input-json file://fh_exp.json --region %REG%
del fh_exp.json

echo [4/4] Watch it come up (Ctrl+C to stop watching). The URL looks like https://fraud-hunter-xxxx.ecs.%REG%.on.aws
aws ecs describe-express-gateway-service --region %REG% --service-arn arn:aws:ecs:%REG%:%ACC%:service/default/fraud-hunter --query "service.activeConfigurations[0].ingressPaths[0].endpoint" --output text
endlocal
