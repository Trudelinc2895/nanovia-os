import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('167.114.155.166', username='root', key_filename=r'C:\Users\Alienware\.ssh\id_rsa', timeout=15)

def run(cmd, timeout=20):
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    return (o.read() + e.read()).decode().strip()

# Check API routes
print("=== API routes (from inside container) ===")
out = run('docker exec infra-api-1 python -c "import urllib.request; r=urllib.request.urlopen(\'http://localhost:8010/openapi.json\'); import json; d=json.loads(r.read()); [print(p) for p in d[\'paths\']]" 2>&1')
print(out[:2000])

# Test API health directly
print("\n=== API /health direct test ===")
print(run('docker exec infra-api-1 python -c "import urllib.request; r=urllib.request.urlopen(\'http://localhost:8010/health\'); print(r.read().decode())" 2>&1'))

# Test via Caddy container
print("\n=== API via Caddy (internal) ===")
print(run('docker exec infra-caddy-1 wget -qO- http://api:8010/health 2>&1 || echo "wget failed"'))

# Check Grafana port
print("\n=== Grafana listening port ===")
print(run('docker exec infra-grafana-1 ss -tlnp 2>/dev/null || docker exec infra-grafana-1 netstat -tlnp 2>&1 | head -5'))

# Check Caddy logs for routing
print("\n=== Caddy recent logs ===")
print(run('docker logs infra-caddy-1 --tail 5 2>&1'))

ssh.close()
