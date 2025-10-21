# syntax=docker/dockerfile:1.7

FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

# Dependencies
RUN yum install -y git && yum clean all

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy app code
COPY . ${LAMBDA_TASK_ROOT}

# Entry point for Lambda (module.function)
CMD ["app.lambda_handler.handler"]
