# syntax=docker/dockerfile:1.7
FROM public.ecr.aws/lambda/python:3.13 AS build

WORKDIR /opt/app

# Build toolchain for compiling Python extensions
# Add more -devel packages only if your deps need them (e.g., openssl-devel, libffi-devel)
RUN microdnf install -y gcc gcc-c++ make \
 && microdnf clean all \
 && rm -rf /var/cache/dnf

COPY requirements.txt .

# Build and install all deps into /opt/python (Lambda looks in /var/task at runtime; we’ll copy there)
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt -t /opt/python

# ------------------------------------------------------------

FROM public.ecr.aws/lambda/python:3.13

# Lambda runtime working dir
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy dependencies built in the first stage
COPY --from=build /opt/python/ ${LAMBDA_TASK_ROOT}/

# Copy your app
COPY . ${LAMBDA_TASK_ROOT}

# If you only needed git to pull private repos in requirements, keep it in the build stage.
# If you also need git at runtime, uncomment:
# RUN microdnf install -y git && microdnf clean all && rm -rf /var/cache/dnf

CMD ["app.lambda_handler.handler"]
