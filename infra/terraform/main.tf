terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  project_slug          = var.project_name
  analysis_queue_name   = "${local.project_slug}-analysis-queue"
  lambda_function_name  = "${local.project_slug}-analysis-worker"
  dynamodb_table_name   = "${local.project_slug}-reports"
  eventbridge_rule_name = "${local.project_slug}-weekly-analysis"
}

resource "aws_sqs_queue" "analysis_queue" {
  name                       = local.analysis_queue_name
  visibility_timeout_seconds = 900
  message_retention_seconds  = 1209600
  receive_wait_time_seconds  = 10
}

resource "aws_dynamodb_table" "analysis_reports" {
  name         = local.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "pk"
  range_key = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  tags = merge(var.default_tags, {
    "Name" = local.dynamodb_table_name
  })
}

resource "aws_iam_role" "lambda_role" {
  name = "${local.lambda_function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.default_tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_custom_policy" {
  name = "${local.lambda_function_name}-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SQSReceive"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.analysis_queue.arn
      },
      {
        Sid    = "DynamoDBAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.analysis_reports.arn
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "analysis_lambda" {
  name              = "/aws/lambda/${local.lambda_function_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "analysis_worker" {
  function_name = local.lambda_function_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 900

  filename         = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

  environment {
    variables = {
      AWS_REGION             = var.aws_region
      ANALYSIS_QUEUE_URL     = aws_sqs_queue.analysis_queue.url
      DYNAMODB_TABLE_NAME    = aws_dynamodb_table.analysis_reports.name
      APP_ENV                = var.app_env
      APP_LOG_LEVEL          = var.app_log_level
      GEMINI_API_KEY         = var.gemini_api_key
      GEMINI_MODEL_NAME      = var.gemini_model_name
      GEMINI_VISION_MODEL_NAME = var.gemini_vision_model_name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy.lambda_custom_policy
  ]
}

resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn  = aws_sqs_queue.analysis_queue.arn
  function_name     = aws_lambda_function.analysis_worker.arn
  batch_size        = 5
  maximum_batching_window_in_seconds = 10
}

resource "aws_cloudwatch_event_rule" "weekly_analysis" {
  name                = local.eventbridge_rule_name
  schedule_expression = var.proactive_schedule_expression
  is_enabled          = true
}

resource "aws_cloudwatch_event_target" "weekly_analysis_target" {
  rule      = aws_cloudwatch_event_rule.weekly_analysis.name
  target_id = "analysis-lambda"
  arn       = aws_lambda_function.analysis_worker.arn

  input = jsonencode({
    action = "run_proactive_analysis"
  })
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.analysis_worker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_analysis.arn
}

output "analysis_queue_url" {
  value       = aws_sqs_queue.analysis_queue.url
  description = "URL of the SQS queue used for analysis jobs."
}

output "dynamodb_table_name" {
  value       = aws_dynamodb_table.analysis_reports.name
  description = "DynamoDB table name storing analysis reports and OAuth tokens."
}

output "analysis_lambda_name" {
  value       = aws_lambda_function.analysis_worker.function_name
  description = "Deployed AWS Lambda function processing analysis jobs."
}
