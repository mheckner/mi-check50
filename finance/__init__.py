from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
import random
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
def startup():
    """application starts up"""
    with App() as app:
        app.get('/').status(200)

@check50.check(startup)
def register_page():
    """register page has all required elements"""
    with App() as app:
        app.get('/register').status(200).css_select([
            'input[name=username]',
            'input[name=password]',
            'input[name=confirmation]',
        ])


@check50.check(register_page)
def register_empty_field():
    """registration with an empty field fails"""
    users = [
        ("", "secret", "secret"),
        ("check50", "secret", ""),
        ("check50", "", "")
    ]
    with App() as app:
        for u in users:
            app.register(*u).status(400)


@check50.check(register_page)
def register_password_mismatch():
    """registration with password mismatch fails"""
    with App() as app:
        app.register("check50", "secret_123!", "secret_999!").status(400)


"""
We operate on the student's db. The structure is unkown.
We cannot drop users. So we have reuse the same user over and over.
"""
user = ['check50', 'secret_123!', 'secret_123!']
@check50.check(register_page)
def register():
    """registering user succeeds"""
    global user
    new_user = [
        'check50_' + str(random.randint(100,999)),
        'check50_123!',
        'check50_123!',
    ]
    with App() as app:
        app.register(*new_user).status(200)
        # Register in case the test runs for the first time
        app.register(*user)


@check50.check(register)
def register_duplicate_username():
    """registration rejects duplicate username"""
    global user
    with App() as app:
        app.register(*user).status(400)


class App():
    def __init__(self):
        self.session = requests_unixsocket.Session()
        self.response = None

    def __enter__(self):
        """We need to close the socket in case of an exception"""

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

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.proc.terminate()
        self.proc.wait(timeout=5)
        os.remove('app.sock')

    def _send(self, method, route, **kwargs):
        prefix = 'http+unix://app.sock'
        url = prefix + route
        try:
            kwargs.setdefault('allow_redirects', False)
            self.response = self.session.request(method=method, url=url,
                **kwargs)

            redirects = 0
            while self.response.is_redirect and redirects < 3:
                redirects += 1
                req = self.response.next
                if req.path_url.startswith('/'):
                    req.url = prefix + self.response.next.url
                self.response = self.session.send(req)
        except requests.exceptions.ConnectionError:
            raise check50.Failure('Server Connection failed.',
                help='Maybe the Server did not start')

    def get(self, route, **kwargs):
        self._send('get', route, **kwargs)
        return self

    def post(self, route, **kwargs):
        self._send('post', route, **kwargs)
        return self

    def status(self, code):
        if (self.response.status_code != code):
            raise check50.Failure(f'expected status code {code} but got ' +
                f'{self.response.status_code}')
        return self

    def css_select(self, selectors):
        soup = BeautifulSoup(self.response.content)

        missing = []
        for s in selectors:
            if not soup.select_one(s):
                missing.append(s)

        if missing:
            raise check50.Failure(f'expect to find html elements matching ' +
                    ', '.join(missing))
        return self

    def register(self, username, password, confirmation):
        data = {
            'username': username,
            'password': password,
            'confirmation': confirmation,
        }
        self.post('/register', data=data)
        return self
