# ═══════════════════════════════════════════════════════════════════════════════
# DEPLOYMENT CONFIGURATION — update these 3 values before running cdk deploy
# ═══════════════════════════════════════════════════════════════════════════════

# Your AWS account ID (12-digit number)
AWS_ACCOUNT = "<your-aws-account-id>"

# AWS region to deploy into
AWS_REGION = "us-east-1"

# S3 bucket name — must be globally unique.
# Default uses account ID as suffix to guarantee uniqueness.
# Change only if you need a custom name.
APP_BUCKET_NAME = f"adua-mysql-upgrade-{AWS_ACCOUNT}"

# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Allowed browser origins for API Gateway CORS (do NOT use "*").
# On the very first deploy the Amplify app ID is not yet known, so the API is
# deployed with the placeholder below. After the UI stack finishes, copy the
# Amplify app URL from the "AmplifyAppUrl" output and set it here, then redeploy
# the API stack so CORS is locked to your real UI origin.
#
# Example: ["https://main.d1a2b3c4d5e6.amplifyapp.com"]
UI_ALLOWED_ORIGINS = [
    o.strip() for o in
    "https://main.PLACEHOLDER.amplifyapp.com".split(",")
    if o.strip()
]

# Initial Cognito user created so operators can log in immediately after deploy.
# The user is created with a temporary password that MUST be changed on first
# login. Leave email blank to skip auto-creating a user (create users manually
# in the Cognito console instead).
COGNITO_INITIAL_USER_EMAIL = ""
