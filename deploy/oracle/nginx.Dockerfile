# SPDX-License-Identifier: Apache-2.0
FROM nginxinc/nginx-unprivileged@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
USER root
RUN apk upgrade --no-cache && apk add --no-cache 'brotli-libs>=1.2.1-r0'
USER 101:101
