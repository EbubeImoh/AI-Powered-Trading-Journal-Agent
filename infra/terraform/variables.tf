variable "project_name" {
  description = "Base name applied to infrastructure resources."
  type        = string
}

variable "aws_region" {
  description = "AWS region for deployment."
  type        = string
  default     = "us-east-1"
}

variable "lambda_package_path" {
  description = "Path to the packaged Lambda deployment artifact (zip file)."
  type        = string
}

variable "app_env" {
  description = "Logical environment name for the application."
  type        = string
  default     = "production"
}

variable "app_log_level" {
  description = "Log level for application components."
  type        = string
  default     = "INFO"
}

variable "default_tags" {
  description = "Default tags applied to all resources."
  type        = map(string)
  default     = {}
}

variable "proactive_schedule_expression" {
  description = "Schedule expression for proactive weekly analyses."
  type        = string
  default     = "cron(0 0 ? * SUN *)"
}

variable "gemini_api_key" {
  description = "API key for Gemini model access."
  type        = string
  sensitive   = true
}

variable "gemini_model_name" {
  description = "Text model name for Gemini-based reasoning."
  type        = string
  default     = "gemini-1.5-pro"
}

variable "gemini_vision_model_name" {
  description = "Vision model name for Gemini image analysis."
  type        = string
  default     = "gemini-1.5-flash"
}
