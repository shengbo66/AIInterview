"""POC configuration."""
import os
from dotenv import load_dotenv

load_dotenv(override=True)

REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("POC_S3_BUCKET", "interviewer-poc-audio")

CLAUDE_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
CLAUDE_TEMPERATURE = 0.3
CLAUDE_MAX_TOKENS = 1500

POLLY_VOICE_ZH = "Zhiyu"
POLLY_VOICE_EN = "Joanna"
POLLY_ENGINE = "neural"

TRANSCRIBE_POLL_INTERVAL_SEC = 1
TRANSCRIBE_TIMEOUT_SEC = 120

RUBRIC_VERSION = "v1.0"

PRICING = {
    "transcribe_call_analytics_per_min": 0.024,
    "claude_sonnet_input_per_1m": 3.0,
    "claude_sonnet_output_per_1m": 15.0,
    "polly_neural_per_1m_char": 16.0,
}
