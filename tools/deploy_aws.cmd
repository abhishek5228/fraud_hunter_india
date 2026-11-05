@echo off
rem Deploy Fraud Hunter to AWS App Runner from Windows CMD.
rem Usage:  tools\deploy_aws.cmd YOUR_API_KEY https://your-frontend-origin [region]
rem Needs:  Docker Desktop running, and AWS CLI set up (aws configure).
setlocal
set KEY=%~1
set ORG=%~2
set REG=%~3
if "%REG%"=="" set REG=ap-south-1
if "%KEY%"=="" (echo Usage: tools\deploy_aws.cmd API_KEY ORIGIN [region] & exit /b 1)
if "%ORG%"=="" set ORG=*

for /f %%a in ('aws sts get-caller-identity --query Account --output text') do set ACC=%%a
if "%ACC%"=="" (echo AWS login failed. Run: aws configure & exit /b 1)
set HOST=%ACC%.dkr.ecr.%REG%.amazonaws.com
set IMG=%HOST%/fraud-hunter:latest
echo Account %ACC%, region %REG%

echo [1/6] ECR repository
aws ecr create-repository --repository-name fraud-hunter --region %REG% >nul 2>&1

echo [2/6] Build and push the image
aws ecr get-login-password --region %REG% | docker login --username AWS --password-stdin %HOST%
if errorlevel 1 exit /b 1
docker build -t fraud-hunter . || exit /b 1
docker tag fraud-hunter %IMG% || exit /b 1
docker push %IMG% || exit /b 1

echo [3/6] Role that lets App Runner pull the image
aws iam create-role --role-name fh-apprunner-ecr --assume-role-policy-document file://tools/aws/trust.json >nul 2>&1
aws iam attach-role-policy --role-name fh-apprunner-ecr --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
for /f %%a in ('aws iam get-role --role-name fh-apprunner-ecr --query Role.Arn --output text') do set ROLE=%%a
timeout /t 10 /nobreak >nul

echo [4/6] One instance only (the feature store lives in memory)
for /f %%a in ('aws apprunner create-auto-scaling-configuration --auto-scaling-configuration-name fh-one --min-size 1 --max-size 1 --max-concurrency 100 --region %REG% --query AutoScalingConfiguration.AutoScalingConfigurationArn --output text') do set ASC=%%a

echo [5/6] Create the service
powershell -NoProfile -Command "(Get-Content tools\aws\service.json -Raw).Replace('__ROLE__','%ROLE%').Replace('__IMG__','%IMG%').Replace('__KEY__','%KEY%').Replace('__ORG__','%ORG%').Replace('__ASC__','%ASC%') | Set-Content fh_svc.json -Encoding ascii"
aws apprunner create-service --cli-input-json file://fh_svc.json --region %REG% --query Service.ServiceUrl --output text
del fh_svc.json

echo [6/6] Wait 3 to 5 minutes, then open the https URL printed above and run:
echo   set FH_URL=https://THE_URL ^& set FH_API_KEY=%KEY% ^& python tools\preflight.py
endlocal
