import requests
import subprocess
import time

import check50

@check50.check()
def app_exists():
    """app.js exists"""
    check50.exists("app.js")

@check50.check(app_exists)
def npm_install():
    """install node modules"""
    check50.exists("package.json")
    check50.exists("package-lock.json")
    check50.run("npm install").exit(code=0, timeout=10)
    check50.exists("node_modules")

@check50.check(npm_install)
def endpoint_index():
    """Route / works"""
    with App() as app:
        r = app.get('/')
        if r.status_code != 200:
            raise check50.Failure(f'Request failed with Code {r.status_code}')

class App(object):
    def __init__(self):
        self.cmd = ['node', 'app.js']

    def __enter__(self):
        self.proc = subprocess.Popen(self.cmd)

        ## Wait for server to start
        ## XXX: dirty hack
        time.sleep(1)

        return self

    def get(self, route):
        try:
            return requests.get(f'http://localhost:3000{route}')
        except requests.exceptions.ConnectionError:
            raise check50.Failure('There is no server running on port 3000')

    def __exit__(self, type, value, traceback):
        self.proc.kill()
