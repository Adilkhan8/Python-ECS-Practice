# SQL Server Database Attachment for ECS Containers
# Overview

This repository is designed to attach a SQL Server database (.mdf or .bak file) to a SQL Server Express instance running within an Amazon ECS container using Python.

It can also be integrated into an AWS Step Functions workflow to automate database attachment and restoration as part of a larger orchestration process.

Prerequisites

Before using this repository, ensure that the following AWS resources are already configured:

* An Amazon ECR repository
* An Amazon ECS cluster
* An Amazon ECS Task Definition
* An AWS Step Functions state machine (optional, for workflow integration)
# How It Works
* Upload or provide the SQL Server database file (.mdf or .bak).
* Execute the Python-based process within the ECS container.
* The script attaches or restores the database to the SQL Server Express instance.
* Optionally, invoke the process through AWS Step Functions for automated execution within a workflow.
# Use Cases
* Automated SQL Server database restoration in ECS environments
* Database migration and deployment workflows
* Integration with AWS Step Functions for end-to-end automation
* Development and testing environments requiring dynamic database attachment
* Integration with AWS Services

This solution can be incorporated into existing AWS workflows that utilize:

* Amazon ECR for container image storage
* Amazon ECS for container orchestration
* AWS Step Functions for workflow automation

By leveraging these services, database attachment and restoration tasks can be executed reliably and consistently within containerized environments.
