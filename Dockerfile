# syntax=docker/dockerfile:1.7
FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

# Install git and pip dependencies
RUN yum install -y git && yum clean all

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy your Flask app
COPY . ${LAMBDA_TASK_ROOT}

# Entry point for Lambda
CMD ["app.lambda_handler.handler"]
