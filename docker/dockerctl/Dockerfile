# dockerctl (spec 021, research R4; contracts/dockerctl.md): ajusta a RAM do container do
# ComfyUI pelo docker.sock. Só a stdlib, sem shell no comando. O usuário (1000:<gid do docker>),
# o read_only, o cap_drop e o no-new-privileges vêm do compose.
FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY server.py /app/server.py

EXPOSE 8080
CMD ["python", "/app/server.py"]
