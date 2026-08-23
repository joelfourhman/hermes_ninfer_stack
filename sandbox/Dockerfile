FROM ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517

ARG DEBIAN_FRONTEND=noninteractive
ARG SANDBOX_UID=1000
ARG SANDBOX_GID=1000

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        coreutils \
        curl \
        git \
        jq \
        nodejs \
        npm \
        openssh-client \
        openssh-server \
        procps \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        tar \
        tini \
        unzip \
        wget \
    && rm -rf /var/lib/apt/lists/* \
    && case "${SANDBOX_UID}:${SANDBOX_GID}" in \
         *[!0-9:]*|:*|*:) echo "Sandbox UID/GID must be numeric" >&2; exit 1 ;; \
       esac \
    && if [ "${SANDBOX_UID}" -lt 1000 ] || [ "${SANDBOX_UID}" -gt 60000 ] \
         || [ "${SANDBOX_GID}" -lt 1000 ] || [ "${SANDBOX_GID}" -gt 60000 ]; then \
         echo "Sandbox UID/GID must both be from 1000 through 60000" >&2; exit 1; \
       fi \
    && existing_group="$(getent group "${SANDBOX_GID}" | cut -d: -f1 || true)" \
    && if [ -n "$existing_group" ] && [ "$existing_group" != agent ]; then \
         if [ "$existing_group" != ubuntu ]; then \
           echo "Sandbox GID ${SANDBOX_GID} is already owned by unexpected group $existing_group" >&2; exit 1; \
         fi; \
         groupmod --new-name agent ubuntu; \
       elif [ -z "$existing_group" ]; then \
         groupadd --gid "${SANDBOX_GID}" agent; \
       fi \
    && existing_user="$(getent passwd "${SANDBOX_UID}" | cut -d: -f1 || true)" \
    && if [ -n "$existing_user" ] && [ "$existing_user" != agent ]; then \
         if [ "$existing_user" != ubuntu ]; then \
           echo "Sandbox UID ${SANDBOX_UID} is already owned by unexpected user $existing_user" >&2; exit 1; \
         fi; \
         usermod --login agent --home /home/agent --move-home --shell /bin/bash ubuntu; \
         usermod --gid "${SANDBOX_GID}" agent; \
       elif [ -z "$existing_user" ]; then \
         useradd --uid "${SANDBOX_UID}" --gid "${SANDBOX_GID}" --create-home --shell /bin/bash agent; \
       fi \
    && usermod --groups "" agent \
    && passwd --delete agent

COPY sshd_config /etc/ssh/sshd_config
COPY entrypoint.sh /usr/local/bin/hermes-sandbox-entrypoint

RUN chmod 0755 /usr/local/bin/hermes-sandbox-entrypoint \
    && mkdir -p /workspace /etc/ssh/host-keys \
    && chown agent:agent /workspace

EXPOSE 2222
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/hermes-sandbox-entrypoint"]
CMD ["serve"]
