FROM python:3.12-slim

# Acceptance fixture only. Not a production runtime image.
# pip requires a PEP 427 wheel filename; the build context uses a stable copy
# name so the Dockerfile does not depend on dist/ layout.
COPY kultrun.whl /tmp/kultrun-0.1.0-py3-none-any.whl
RUN pip install --no-cache-dir /tmp/kultrun-0.1.0-py3-none-any.whl \
    && rm /tmp/kultrun-0.1.0-py3-none-any.whl
