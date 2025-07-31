"""
Application Configuration Settings

Defines the application configuration using Pydantic's BaseSettings,
loading environment variables from a `.env` file by default.

Includes:

- Security keys and debug flags
- AWS credentials and region
- MongoDB credentials and database info
- AWS Cognito OAuth2 client settings
- OAuthlib transport configuration

The `Settings` class enforces strict environment variable validation to
catch typos or missing values early.

A global `settings` instance is created for convenient import across the app.
"""

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = Field(..., alias='SECRET_KEY')
    debug: bool = Field(default=False, alias='DASH_DEBUG')
    env: str = Field(default='development', alias='DASH_ENV')

    # Cognito settings
    cognito_client_id: str = Field(..., alias='COGNITO_CLIENT_ID')
    cognito_client_secret: str = Field(..., alias='COGNITO_CLIENT_SECRET')
    cognito_domain: str = Field(..., alias='COGNITO_DOMAIN')
    cognito_redirect_uri: str = Field(..., alias='COGNITO_REDIRECT_URI')
    cognito_logout_uri: str = Field(
        default='http://localhost:7777', alias='COGNITO_LOGOUT_URI'
    )
    cognito_user_pool_id: str = Field(..., alias='COGNITO_USER_POOL_ID')

    # AWS / Mongo / Other APIs
    aws_access_key_id: str = Field(..., alias='AWS_ACCESS_KEY_ID')
    aws_secret_access_key: str = Field(..., alias='AWS_SECRET_ACCESS_KEY')
    aws_region: str = Field(..., alias='AWS_REGION')

    mongo_initdb_root_username: str = Field(..., alias='MONGO_INITDB_ROOT_USERNAME')
    mongo_initdb_root_password: str = Field(..., alias='MONGO_INITDB_ROOT_PASSWORD')
    mongo_initdb_database: str = Field(..., alias='MONGO_INITDB_DATABASE')

    # OAuthlib setting (optional)
    oauthlib_insecure_transport: str = Field(
        default='0', alias='OAUTHLIB_INSECURE_TRANSPORT'
    )

    model_config = ConfigDict(env_file='.env', extra='forbid', frozen=True)


# Create one global settings instance to import elsewhere
settings = Settings()
