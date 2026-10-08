# SAP RFP agent service (FastAPI). LibreOffice is not needed at runtime.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WORKSPACE_DIR=/data/workspace \
    ASSETS_DIR=/app/assets POLICY_DIR=/app/policy SKILLS_DIR=/app/skills
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY assets ./assets
COPY policy ./policy
COPY skills ./skills
COPY ui ./ui
COPY scripts ./scripts

VOLUME ["/data"]
EXPOSE 8000
# The UI runs as a second container from the same image:
#   docker run ... -e API_URL=http://api:8000 <image> streamlit run ui/streamlit_app.py --server.port 8501
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
