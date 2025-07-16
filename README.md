# Dashboard

## Description

This is a global dashboard to run various api !

## Usage

### Test the prod locally

1. Build the image

```bash
docker build -f Dockerfile.prod -t fsds-dashboard .
```

2. Run it locally

```bash
docker run --name fsds-dashboard-container -p 7777:7777 fsds-dashboard
```

Access the local Dashboard on [0.0.0.0:7777](http://0.0.0.0:7777).

## .env details

The .env file looks like this:

MONGO_INITDB_ROOT_USERNAME=
MONGO_INITDB_ROOT_PASSWORD=
MONGO_INITDB_DATABASE=

# AWS access

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=

where the Mongo init DB allows to initialize the database simply with username and password
and AWS ID/KEY are taken from an AWS IAM user with AWS S3 Full access permissions

# select debug mode or not for the Dash app

DASH_DEBUG=True

# Use Flask when in development, else require gunicorn run

DASH_ENV="development"
