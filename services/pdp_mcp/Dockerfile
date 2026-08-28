ARG PDP_DOCKER_REGISTRY=docker.arvancloud.ir/library
FROM ${PDP_DOCKER_REGISTRY}/python:3.13-slim
LABEL io.pdpone.component="mcp"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py server_core.py server_procurement.py procurement_tools.py procurement_analysis_tools.py automation_tools.py deployment_queue.py deployment_coordinator.py promotion_control_v3.py promotion_control_v3_hardening.py exact_candidate_promotion_tools.py health_tools.py route_diagnostics_tools.py public_edge_status.py ./
EXPOSE 8010
CMD ["python", "server_procurement.py"]
