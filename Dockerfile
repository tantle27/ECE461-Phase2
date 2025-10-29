# syntax=docker/dockerfile:1.7
FROM public.ecr.aws/lambda/python:3.13

WORKDIR ${LAMBDA_TASK_ROOT}

# Install git and pip dependencies
RUN microdnf install -y git && microdnf clean all && rm -rf /var/cache/dnf

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy your Flask app
COPY . ${LAMBDA_TASK_ROOT}

# Entry point for Lambda
CMD ["app.lambda_handler.handler"]
