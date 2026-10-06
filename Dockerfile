FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /work

# The wheel is included in the prepared source archive. Runtime installation
# uses only that local artifact, with no package-index access or dependencies.
COPY dist/verifyrank-0.2.0-py3-none-any.whl /tmp/verifyrank-0.2.0-py3-none-any.whl
RUN python -m pip install --no-index --no-deps --no-cache-dir /tmp/verifyrank-0.2.0-py3-none-any.whl
COPY examples/synthetic/ /work/examples/synthetic/

ENTRYPOINT ["python", "-m", "verifyrank"]
CMD ["--help"]
