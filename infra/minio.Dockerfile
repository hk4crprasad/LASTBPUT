FROM golang:1.24.2-bookworm AS build
ARG MINIO_VERSION=RELEASE.2025-04-22T22-12-26Z
RUN GOBIN=/out go install github.com/minio/minio@${MINIO_VERSION}
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/local/bin/minio
RUN useradd -u 10001 -m minio && mkdir /data && chown minio /data
USER minio
ENTRYPOINT ["minio"]
CMD ["server", "/data"]
