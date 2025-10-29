# syntax=docker/dockerfile:1.7

# ---------- Build stage ----------
FROM public.ecr.aws/lambda/python:3.13 AS build
WORKDIR /opt/app

# Toolchain for any wheels you need to compile
RUN microdnf install -y gcc gcc-c++ make \
 && microdnf clean all \
 && rm -rf /var/cache/dnf

COPY requirements.txt .

# Install all deps into /opt/python so they can be copied to the final image
# Ensure git-related tools are present in site-packages
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt gitpython flake8 boto3

# ---------- Runtime stage ----------
FROM public.ecr.aws/lambda/python:3.13

# Lambda looks in /var/task by default
WORKDIR ${LAMBDA_TASK_ROOT}

# Install git for runtime repo analysis
RUN microdnf install -y git ca-certificates \
 && microdnf clean all \
 && rm -rf /var/cache/dnf

# Make sure GitPython finds git and no interactive prompts occur
ENV GIT_PYTHON_GIT_EXECUTABLE=/usr/bin/git \
    GIT_PYTHON_REFRESH=quiet \
    GIT_TERMINAL_PROMPT=0

# Copy dependencies and app code
COPY --from=build /opt/python/ ${LAMBDA_TASK_ROOT}/
COPY . ${LAMBDA_TASK_ROOT}

# Handler
CMD ["app.lambda_handler.handler"]