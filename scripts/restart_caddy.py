import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('167.114.155.166', username='root', key_filename=r'C:\Users\Alienware\.ssh\id_rsa', timeout=15)

def run(cmd, timeout=30):
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    out = o.read().decode().strip()
    err = e.read().decode().strip()
    return out or err

# git pull + restart caddy only
print('[1] git pull...')
print(run('cd /opt/kt-monetization-os && git pull origin main 2>&1'))

print('\n[2] Verify Caddyfile on VPS...')
print(run('head -5 /opt/kt-monetization-os/infra/docker/Caddyfile'))

print('\n[3] Restart Caddy...')
print(run('docker restart infra-caddy-1 2>&1'))
time.sleep(5)

print('\n[4] Caddy logs after restart...')
print(run('docker logs infra-caddy-1 --tail 8 2>&1'))

print('\n[5] All container status...')
print(run("docker ps --format 'table {{.Names}}\t{{.Status}}'"))

print('\n[6] API logs check...')
print(run('docker logs infra-api-1 --tail 5 2>&1'))

print('\n[7] Public HTTP test...')
code = run('curl -s -o /dev/null -w "%{http_code}" http://167.114.155.166/ --max-time 5 2>/dev/null || echo 000')
print(f'  http://167.114.155.166/ → HTTP {code}')

code2 = run('curl -s -o /dev/null -w "%{http_code}" http://167.114.155.166:8010/health --max-time 5 2>/dev/null || echo 000')
print(f'  http://167.114.155.166:8010/health → HTTP {code2}')

# Test via docker network
print('\n[8] API test from inside network...')
out = run('docker exec infra-api-1 python -c "import urllib.request; r=urllib.request.urlopen(\'http://localhost:8010/health\'); print(r.read().decode())" 2>/dev/null || echo FAIL')
print(f'  API /health: {out}')

ssh.close()
print('\n=== DONE ===')
