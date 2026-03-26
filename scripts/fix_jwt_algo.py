import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('167.114.155.166', username='root', key_filename=r'C:\Users\Alienware\.ssh\id_rsa', timeout=15)

def run(cmd):
    _, o, e = ssh.exec_command(cmd, timeout=20)
    return (o.read() + e.read()).decode().strip()

print("=== JWT vars in .env ===")
print(run("grep -i jwt /opt/kt-monetization-os/.env"))

# Fix RS256 -> HS256
run("sed -i 's/JWT_ALGORITHM=RS256/JWT_ALGORITHM=HS256/' /opt/kt-monetization-os/.env")
print("\nAfter fix:")
print(run("grep JWT_ALGORITHM /opt/kt-monetization-os/.env"))

# Restart api
print("\nRestarting api container...")
print(run("docker restart infra-api-1"))
time.sleep(10)
print(run("docker logs infra-api-1 --tail 6 2>&1"))

# Also fix local .env
ssh.close()
print("\nDone")
