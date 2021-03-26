import check50
import requests
import subprocess
import threading
import time

@check50.check()
def exists():
    """app.js exists"""
    check50.exists("app.js")

@check50.check(exists)
def npm():
    """install node modules"""
    check50.exists("package.json")
    check50.exists("package-lock.json")
    check50.run("npm install").exit(code=0, timeout=10)
    check50.exists("node_modules")

@check50.check(npm)
def endpoint_index():
    """Route / works"""
    proc = subprocess.Popen(['node', 'app.js'])

    # Wait for server to start
    # XXX: dirty hack
    time.sleep(1)

    try:
        r = requests.get('http://localhost:3000')
        if r.status_code != 200:
            raise check50.Failure(f'Request failed with Code {r.status_code}')
    except requests.exceptions.ConnectionError:
        raise check50.Failure('There is no server running on port 3000')
    finally:
        proc.kill()
