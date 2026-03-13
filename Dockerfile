# Development image: extends the official pretix standalone image and
# installs this plugin in editable mode from a volume mount.
#
# For production use, build a final image with:
#   COPY . /pretix-email-restrictions
#   RUN pip3 install /pretix-email-restrictions
FROM pretix/standalone:stable

USER root

# Create a stable directory for the editable install metadata.
# The actual source is bind-mounted at runtime (see docker-compose.yml).
RUN mkdir -p /pretix-email-restrictions
WORKDIR /pretix-email-restrictions

# Copy only the packaging metadata so the editable install is registered.
# The source tree is mounted over this directory at runtime, so code
# changes are picked up without rebuilding the image.
COPY pyproject.toml ./
COPY pretix_email_restrictions/__init__.py ./pretix_email_restrictions/__init__.py

RUN pip3 install --no-deps -e .

USER pretixuser

WORKDIR /
