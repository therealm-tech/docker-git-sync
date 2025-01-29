ARG python_version=3.13.1

FROM python:"$python_version-alpine3.21"

SHELL ["/bin/sh", "-euo", "pipefail", "-c"]

RUN \
  apk update \
  && apk add --no-cache \
    git=2.47.2-r0 \
    openssh-client=9.9_p1-r2 \
  && adduser -D -g git -u 1000 git

COPY --chown=git:git git-sync /tmp/git-sync

RUN \
  pip install \
    --no-cache-dir \
    /tmp/git-sync \
  && mkdir /home/git/repo \
  && chown -R git: /home/git/repo \
  && rm -rf /tmp/git-sync

USER git

WORKDIR /home/git/repo

ENTRYPOINT ["git-sync"]
