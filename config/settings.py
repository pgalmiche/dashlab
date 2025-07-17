from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = Field(..., alias="SECRET_KEY")
    debug: bool = Field(default=False, alias="DASH_DEBUG")
    env: str = Field(default="development", alias="DASH_ENV")

    # Cognito settings
    cognito_client_id: str = Field(..., alias="COGNITO_CLIENT_ID")
    cognito_client_secret: str = Field(..., alias="COGNITO_CLIENT_SECRET")
    cognito_domain: str = Field(..., alias="COGNITO_DOMAIN")
    cognito_redirect_uri: str = Field(..., alias="COGNITO_REDIRECT_URI")
    cognito_logout_uri: str = Field(
        default="http://localhost:7777", alias="COGNITO_LOGOUT_URI"
    )
    cognito_user_pool_id: str = Field(..., alias="COGNITO_USER_POOL_ID")

    # AWS / Mongo / Other APIs
    aws_access_key_id: str = Field(..., alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(..., alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(..., alias="AWS_REGION")

    mongo_initdb_root_username: str = Field(..., alias="MONGO_INITDB_ROOT_USERNAME")
    mongo_initdb_root_password: str = Field(..., alias="MONGO_INITDB_ROOT_PASSWORD")
    mongo_initdb_database: str = Field(..., alias="MONGO_INITDB_DATABASE")

    # OAuthlib setting (optional)
    oauthlib_insecure_transport: str = Field(
        default="0", alias="OAUTHLIB_INSECURE_TRANSPORT"
    )

    class Config:
        env_file = ".env"
        extra = "forbid"  # helps catch typoed or unexpected env vars


# Create one global settings instance to import elsewhere
settings = Settings()
