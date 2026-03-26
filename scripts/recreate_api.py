import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('167.114.155.166', username='root', key_filename=r'C:\Users\Alienware\.ssh\id_rsa', timeout=15)

def run(cmd, timeout=30):
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    return (o.read() + e.read()).decode().strip()

# Verify .env has HS256
print("JWT_ALGORITHM in .env:", run("grep JWT_ALGORITHM /opt/kt-monetization-os/.env"))

# Force recreate api container to re-read env_file
print("\nRecreating api container (to reload .env)...")
result = run(
    "cd /opt/kt-monetization-os && "
    "docker compose -f infra/docker-compose.prod.yml "
    "--env-file /opt/kt-monetization-os/.env "
    "up -d --force-recreate api 2>&1",
    timeout=60
)
print(result[-500:] if len(result) > 500 else result)

time.sleep(10)

# Verify JWT_ALGORITHM loaded in container
print("\nJWT_ALGORITHM in container env:")
print(run("docker exec infra-api-1 env | grep JWT_ALGORITHM"))

# Check startup
print("\nStartup logs:")
print(run("docker logs infra-api-1 --tail 5 2>&1"))

ssh.close()
