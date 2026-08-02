ARG PDP_DOCKER_REGISTRY=docker.arvancloud.ir/library
FROM ${PDP_DOCKER_REGISTRY}/python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py server_procurement.py procurement_tools.py procurement_analysis_tools.py automation_tools.py deployment_queue.py ./
EXPOSE 8010
CMD ["python", "server_procurement.py"]
