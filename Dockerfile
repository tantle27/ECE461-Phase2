# syntax=docker/dockerfile:1.7

# ---------- Build stage ----------
FROM public.ecr.aws/lambda/python:3.13 AS build
WORKDIR /opt/app

# Toolchain only for building wheels if needed
RUN microdnf install -y gcc gcc-c++ make \
 && microdnf clean all \
 && rm -rf /var/cache/dnf

COPY requirements.txt .

# Install all dependencies into /opt/python
# Lambda will include these when we copy them into /var/task in the final image
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt -t /opt/python \
 && pip install --no-cache-dir gitpython flake8 boto3 -t /opt/python

# ---------- Runtime stage ----------
FROM public.ecr.aws/lambda/python:3.13
WORKDIR ${LAMBDA_TASK_ROOT}

# If you need git at runtime, install it here
RUN microdnf install -y git ca-certificates \
 && microdnf clean all \
 && rm -rf /var/cache/dnf

# Make GitPython happy and stop git prompts
ENV GIT_PYTHON_GIT_EXECUTABLE=/usr/bin/git \
    GIT_PYTHON_REFRESH=quiet \
    GIT_TERMINAL_PROMPT=0

# Bring in site-packages from the build stage
COPY --from=build /opt/python/ ${LAMBDA_TASK_ROOT}/

# Copy your application code last for better layer cache
COPY . ${LAMBDA_TASK_ROOT}

# Lambda handler
CMD ["app.lambda_handler.handler"]