import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('167.114.155.166', username='root', key_filename=r'C:\Users\Alienware\.ssh\id_rsa', timeout=15)

def run(cmd):
    _, o, _ = ssh.exec_command(cmd)
    return o.read().decode().strip()

print('=== STATUS CONTAINERS ===')
print(run("docker ps --format 'table {{.Names}}\t{{.Status}}'"))

print()
print('=== TESTS SANTE ===')
tests = [
    ('API FastAPI',      'infra-api-1',             'curl -s http://localhost:8010/health'),
    ('API root',         'infra-api-1',             'curl -s http://localhost:8010/'),
    ('Next.js Web',      'infra-web-1',             'curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/'),
    ('Admin stub',       'infra-admin-1',           'curl -s http://localhost:3020/health'),
    ('AI Orchestrator',  'infra-ai-orchestrator-1', 'curl -s http://localhost:8020/health'),
    ('Postgres',         'infra-postgres-1',        'pg_isready -U ktadmin 2>/dev/null || echo checking'),
    ('Redis',            'infra-redis-1',           'redis-cli ping'),
]
for label, container, cmd in tests:
    full_cmd = f'docker exec {container} {cmd} 2>/dev/null || echo "ERR/TIMEOUT"'
    out = run(full_cmd)
    ok = any(x in out.lower() for x in ['ok', '200', 'pong', 'accepting', 'status'])
    icon = '✅' if ok else '⚠️'
    print(f'  {icon} {label:20s}: {out[:100]}')

print()
print('=== CADDY PUBLIC (ports 80/443) ===')
http_code = run('curl -s -o /dev/null -w "%{http_code}" http://167.114.155.166/ --max-time 5 2>/dev/null')
print(f'  HTTP {http_code} → http://167.114.155.166/')

print()
print('=== LOGS API ===')
print(run('docker logs infra-api-1 --tail 15 2>&1'))

print()
print('=== LOGS CADDY ===')
print(run('docker logs infra-caddy-1 --tail 10 2>&1'))

ssh.close()
print()
print('=== DONE ===')
