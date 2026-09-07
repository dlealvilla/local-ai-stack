FROM python:3.12-slim

# Acceptance fixture only. Not a production runtime image.
COPY kultrun.whl /tmp/kultrun.whl
RUN pip install --no-cache-dir /tmp/kultrun.whl && rm /tmp/kultrun.whl
