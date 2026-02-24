FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-matplotlib \
    python3-numpy \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY iperf3_client.py /app/
COPY servers.txt /app/
ENTRYPOINT ["python3", "/app/iperf3_client.py"]
CMD ["--n", "10", "--duration", "20", "--interval", "1", "--servers", "/app/servers.txt"]