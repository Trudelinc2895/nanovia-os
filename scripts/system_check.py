import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('167.114.155.166', username='root', key_filename=r'C:\Users\Alienware\.ssh\id_rsa', timeout=15)

def run(cmd):
    _, o, e = ssh.exec_command(cmd, timeout=20)
    return (o.read() + e.read()).decode().strip()

print("=== Prometheus config ===")
print(run("cat /opt/nanovia-os/infra/monitoring/prometheus.yml 2>/dev/null || echo MISSING"))

print("\n=== DB tables ===")
print(run("docker exec infra-postgres-1 psql -U ktadmin -d ktmonetization -c '\\dt' 2>&1"))

print("\n=== All containers status ===")
print(run("docker ps --format 'table {{.Names}}\t{{.Status}}'"))

ssh.close()

