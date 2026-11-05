FROM alpine:3.22
RUN apk add --no-cache openssh-server openssh-keygen \
    && adduser -D -s /sbin/nologin tunnel \
    && passwd -d tunnel \
    && mkdir -p /run/sshd /var/lib/team-ssh
COPY sshd_config /etc/ssh/sshd_config
COPY start.sh /usr/local/bin/team-sshd
ENTRYPOINT ["sh","/usr/local/bin/team-sshd"]
