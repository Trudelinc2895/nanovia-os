import argparse
import os
import posixpath
import shlex
import sys
from pathlib import Path

import paramiko


SSHD_CONFIG = """# Nanovia OVH rescue SSH config
Port 22
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PermitEmptyPasswords no
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowTcpForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
UsePAM yes
"""

JAIL_LOCAL = """[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
backend = auto

[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
maxretry = 3
bantime = 86400
"""

SYSCTL_HARDENING = """
# Nanovia OVH rescue hardening
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
kernel.dmesg_restrict = 1
"""

APT_AUTO_UPGRADES = """APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
"""

UNATTENDED_UPGRADES = """Unattended-Upgrade::Origins-Pattern {
        "origin=${distro_id},codename=${distro_codename},label=${distro_id}";
        "origin=${distro_id},codename=${distro_codename},label=${distro_id}-Security";
        "origin=${distro_id},codename=${distro_codename}-security,label=${distro_id}-Security";
};

Unattended-Upgrade::Package-Blacklist {
};

Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:30";
Unattended-Upgrade::SyslogEnable "true";
"""


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def read_public_key(key_path: str | None, key_value: str | None) -> str:
    if key_value:
        return key_value.strip()
    if not key_path:
        raise SystemExit("Missing SSH public key. Set --public-key-path or OVH_AUTHORIZED_KEY_PATH.")
    return Path(key_path).read_text(encoding="utf-8").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Secure an OVH VPS while it is booted in rescue mode."
    )
    parser.add_argument("--host", default=os.environ.get("OVH_RESCUE_HOST"))
    parser.add_argument("--user", default=os.environ.get("OVH_RESCUE_USER", "root"))
    parser.add_argument("--password", default=os.environ.get("OVH_RESCUE_PASSWORD"))
    parser.add_argument("--mount-device", default=os.environ.get("OVH_ROOT_DEVICE"))
    parser.add_argument("--mount-point", default=os.environ.get("OVH_MOUNT_POINT", "/mnt/real"))
    parser.add_argument("--public-key-path", default=os.environ.get("OVH_AUTHORIZED_KEY_PATH"))
    parser.add_argument("--public-key", default=os.environ.get("OVH_AUTHORIZED_KEY"))
    parser.add_argument("--new-root-password", default=os.environ.get("OVH_NEW_ROOT_PASSWORD"))
    parser.add_argument("--ssh-port", type=int, default=int(os.environ.get("OVH_RESCUE_PORT", "22")))
    return parser


class RescueSession:
    def __init__(self, host: str, user: str, password: str, port: int) -> None:
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def connect(self) -> None:
        self.client.connect(
            self.host,
            port=self.port,
            username=self.user,
            password=self.password,
            timeout=20,
        )

    def close(self) -> None:
        self.client.close()

    def run(self, command: str, show: bool = True) -> str:
        stdin, stdout, stderr = self.client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()

        if show and out:
            print(f"OUT: {out}")
        if show and err:
            print(f"ERR: {err}", file=sys.stderr)
        if exit_status != 0:
            raise RuntimeError(f"Remote command failed ({exit_status}): {command}")
        return out

    def write_file(self, remote_path: str, content: str, mode: int | None = None) -> None:
        sftp = self.client.open_sftp()
        try:
            with sftp.open(remote_path, "w") as handle:
                handle.write(content)
            if mode is not None:
                sftp.chmod(remote_path, mode)
        finally:
            sftp.close()


def require_arg(name: str, value: str | None) -> str:
    if not value:
        raise SystemExit(f"Missing required value: {name}")
    return value


def ensure_directory(session: RescueSession, path: str) -> None:
    session.run(f"mkdir -p {shell_quote(path)}", show=False)


def mount_root_disk(session: RescueSession, device: str, mount_point: str) -> None:
    ensure_directory(session, mount_point)
    mounts = session.run("mount", show=False)
    if mount_point in mounts:
        session.run(f"umount {shell_quote(mount_point)}", show=False)
    session.run(f"mount {shell_quote(device)} {shell_quote(mount_point)}")


def inject_authorized_key(session: RescueSession, mount_point: str, public_key: str) -> None:
    ssh_dir = posixpath.join(mount_point, "root", ".ssh")
    ensure_directory(session, ssh_dir)
    session.run(f"chmod 700 {shell_quote(ssh_dir)}", show=False)
    session.write_file(posixpath.join(ssh_dir, "authorized_keys"), public_key + "\n", mode=0o600)


def secure_sshd(session: RescueSession, mount_point: str) -> None:
    sshd_path = posixpath.join(mount_point, "etc", "ssh", "sshd_config")
    session.run(f"cp {shell_quote(sshd_path)} {shell_quote(sshd_path + '.bak')}", show=False)
    session.write_file(sshd_path, SSHD_CONFIG)


def update_root_password(session: RescueSession, mount_point: str, new_password: str | None) -> None:
    if not new_password:
        return
    escaped_password = new_password.replace("'", "'\"'\"'")
    session.run(
        f"chroot {shell_quote(mount_point)} bash -lc 'echo root:{escaped_password} | chpasswd'",
        show=False,
    )


def configure_ufw(session: RescueSession, mount_point: str) -> None:
    commands = [
        "apt-get update -qq || true",
        "apt-get install -y -qq ufw || true",
        "ufw --force reset || true",
        "ufw default deny incoming",
        "ufw default allow outgoing",
        "ufw allow 22/tcp",
        "ufw allow 80/tcp",
        "ufw allow 443/tcp",
        "ufw --force enable || true",
    ]
    for command in commands:
        session.run(f"chroot {shell_quote(mount_point)} bash -lc {shell_quote(command)}", show=False)


def configure_fail2ban(session: RescueSession, mount_point: str) -> None:
    fail2ban_dir = posixpath.join(mount_point, "etc", "fail2ban")
    exists = session.run(f"test -d {shell_quote(fail2ban_dir)} && echo yes || echo no", show=False)
    if exists.strip() == "yes":
        session.write_file(posixpath.join(fail2ban_dir, "jail.local"), JAIL_LOCAL)


def configure_unattended_upgrades(session: RescueSession, mount_point: str) -> None:
    commands = [
        "apt-get update -qq || true",
        "apt-get install -y -qq unattended-upgrades apt-listchanges || true",
        "systemctl enable unattended-upgrades || true",
    ]
    for command in commands:
        session.run(f"chroot {shell_quote(mount_point)} bash -lc {shell_quote(command)}", show=False)

    apt_conf_dir = posixpath.join(mount_point, "etc", "apt", "apt.conf.d")
    session.write_file(posixpath.join(apt_conf_dir, "20auto-upgrades"), APT_AUTO_UPGRADES)
    session.write_file(posixpath.join(apt_conf_dir, "50unattended-upgrades"), UNATTENDED_UPGRADES)


def append_sysctl_hardening(session: RescueSession, mount_point: str) -> None:
    sysctl_path = posixpath.join(mount_point, "etc", "sysctl.conf")
    sentinel = "# Nanovia OVH rescue hardening"
    existing = session.run(f"grep -F {shell_quote(sentinel)} {shell_quote(sysctl_path)} || true", show=False)
    if existing.strip():
        return
    append_command = (
        f"cat >> {shell_quote(sysctl_path)} <<'EOF'\n{SYSCTL_HARDENING.strip()}\nEOF"
    )
    session.run(append_command, show=False)


def verify_installation(session: RescueSession, mount_point: str) -> None:
    auth_keys_path = posixpath.join(mount_point, "root", ".ssh", "authorized_keys")
    key_check = session.run(f"head -c 80 {shell_quote(auth_keys_path)}", show=False)
    sshd_check = session.run(
        f"grep -E '^(PasswordAuthentication|PermitRootLogin|PubkeyAuthentication)' "
        f"{shell_quote(posixpath.join(mount_point, 'etc', 'ssh', 'sshd_config'))}",
        show=False,
    )
    print(f"authorized_keys preview: {key_check}...")
    print("sshd_config checks:")
    print(sshd_check)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    host = require_arg("--host", args.host)
    user = require_arg("--user", args.user)
    password = require_arg("--password", args.password)
    mount_device = require_arg("--mount-device", args.mount_device)
    public_key = read_public_key(args.public_key_path, args.public_key)

    session = RescueSession(host=host, user=user, password=password, port=args.ssh_port)
    mounted = False

    try:
        session.connect()
        print("Connected in OVH rescue mode.")

        print("[1/7] Mounting root disk...")
        mount_root_disk(session, mount_device, args.mount_point)
        mounted = True

        print("[2/7] Injecting SSH public key...")
        inject_authorized_key(session, args.mount_point, public_key)

        print("[3/7] Hardening sshd_config...")
        secure_sshd(session, args.mount_point)

        print("[4/7] Updating root password (optional)...")
        update_root_password(session, args.mount_point, args.new_root_password)

        print("[5/7] Configuring UFW...")
        configure_ufw(session, args.mount_point)

        print("[6/7] Configuring fail2ban, automatic security updates, and sysctl...")
        configure_fail2ban(session, args.mount_point)
        configure_unattended_upgrades(session, args.mount_point)
        append_sysctl_hardening(session, args.mount_point)

        print("[7/7] Verifying changes...")
        verify_installation(session, args.mount_point)

        print("\nRescue hardening complete.")
        print("Next steps:")
        print("1. In OVH Manager, switch Netboot back to the local disk.")
        print("2. Reboot the VPS in normal mode.")
        print("3. Log in over SSH with the injected key.")
        return 0
    finally:
        if mounted:
            try:
                session.run(f"umount {shell_quote(args.mount_point)}", show=False)
            except Exception:
                pass
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
