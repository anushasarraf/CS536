FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

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
COPY run_experiment.sh /app/

RUN chmod +x /app/run_experiment.sh

# Default: run the full experiment
ENTRYPOINT ["python3", "/app/iperf3_client.py"]
CMD ["--n", "10", "--duration", "20"]