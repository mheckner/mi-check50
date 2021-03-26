from dotenv import load_dotenv
import os
import requests
import requests_unixsocket
import subprocess
import time

import check50

@check50.check()
def app_exists():
    """app.js exists"""
    check50.exists("app.js")

@check50.check(app_exists)
def env():
    """load environment variables"""
    check50.exists(".env")
    load_dotenv(dotenv_path='.env')
    if not os.getenv("DB_CON_STRING"):
        raise check50.Failure('The file .env does not specify DB_CON_STRING')
    if not os.getenv("API_KEY"):
        raise check50.Failure('The file .env does not specify API_KEY')

@check50.check(env)
def npm_install():
    """install node modules"""
    check50.exists("package.json")
    check50.exists("package-lock.json")
    check50.run("npm install").exit(code=0, timeout=20)
    check50.exists("node_modules")

@check50.check(npm_install)
def route():
    """route / returns 200"""
    with App() as app:
        r = app.get('/')
        if r.status_code != 200:
            raise check50.Failure(f'Request failed with Code {r.status_code}')


class App(object):
    def __init__(self):
        self.session = requests_unixsocket.Session()

    def __enter__(self):
        # check50 starts each different checks in different processes.
        # We need to reload the environment variables in each check.
        load_dotenv(dotenv_path='.env')

        cmd = ['node', 'app.js']
        # Bind the app to a UNIX domain socket to run checks in parallel.
        env = { **os.environ, 'PORT': 'app.sock' }
        self.proc = subprocess.Popen(cmd, env=env)

        # Wait up to 10 seconds for the server to startup.
        for i in range(0,10):
            if self.proc.poll():
                raise check50.Failure(
                        f'Server crashed with code {self.proc.returncode}')
            if os.path.exists('app.sock'):
                break
            time.sleep(1)
        else:
            raise check50.Failure('Server not started within 10 seconds')

        return self

    def get(self, route):
        try:
            return self.session.get(f'http+unix://app.sock{route}')
        except requests.exceptions.ConnectionError:
            raise check50.Failure('Server is not running')

    def __exit__(self, type, value, traceback):
        self.proc.kill()
