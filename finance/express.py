from bs4 import BeautifulSoup
from dotenv import load_dotenv
from random import randint
import check50
import os
import re
import requests
import requests_unixsocket
import subprocess
import time
import urllib.parse


class App():
    def __init__(self):
        self._session = requests_unixsocket.Session()
        self._response = None
        self._proc = None
        self._username = 'check50_' + str(randint(10000000, 99999999))
        self._password = 'check50_123!'
        self._prefix = 'http+unix://app.sock'
        self._max_redirects = 5

    def __enter__(self):
        """
        We need to close the socket in case of an exception.
        Use Context Manager.
        """

        """
        check50 starts each different checks in different processes.
        We need to reload the environment variables in each check.
        """
        load_dotenv(dotenv_path='.env')

        """
        Generate a new user an save it for later usage.

        At the moment the only way to pass data to later checks
        is to write to file, depend on the check and read the file.
        """
        self._username = os.environ.get('CS50_USERNAME', self._username)
        self._password = os.environ.get('CS50_PASSWORD', self._password)
        with open('.env', 'a') as f:
            f.write(f'\n')
            f.write(f'CS50_USERNAME={self._username}\n')
            f.write(f'CS50_PASSWORD={self._password}\n')

        cmd = ['node', 'app.js']
        # Bind the app to a UNIX domain socket to run checks in parallel.
        env = { **os.environ, 'PORT': 'app.sock' }
        self._proc = subprocess.Popen(cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True)

        # Wait up to 10 seconds for the server to startup/create the socket
        for _ in range(0,10):
            if self._proc.poll() is not None:
                self._print_server_log()
                raise check50.Failure(
                        f'Server crashed with code {self._proc.returncode}')
            if os.path.exists('app.sock'):
                break
            time.sleep(1)
        else:
            self._proc.kill()
            raise check50.Failure('Server not started within 10 seconds')
        return self

    def _print_server_log(self):
        out = self._proc.stdout.read()
        for line in out.splitlines():
            check50.log(line)
        err = self._proc.stderr.read()
        for line in err.splitlines():
            check50.log(line)

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self._proc.kill()
        """
        Dependend checks inherit the previous check's filesystem.
        Remove the server socket, so the new app instance does not throw
        an address already inuse error.
        """
        if os.path.exists('app.sock'):
            os.remove('app.sock')

        # Fail check if there are errors on the console
        if exception_type is None:
            err = self._proc.stderr.read()
            if err:
                for line in err.splitlines():
                    check50.log(line)
                raise check50.Failure('Output on STDERR.',
                        help='Fix your errors first.')

    def _send(self, method, route, **kwargs):
        url = self._prefix + route

        """
        We need to prefix redirect urls like '/' or '/login'.
        Therefore disable redirects and follow them manually.
        """
        kwargs.setdefault('allow_redirects', False)

        data = "";
        if "data" in kwargs:
            data = str(kwargs["data"])
        check50.log(("sending {} request to {} with data [{}]").format(method.upper(), route, data))

        try:
            self._response = self._session.request(method=method, url=url,
                **kwargs)

            check50.log(("got response {} for {} request to {}").format(str(self._response.status_code), method.upper(), route, data))

            for _ in range(self._max_redirects):
                if not self._response.is_redirect:
                    break

                req = self._response.next
                req.url = self._prefix_url(self._response.next.url)
                # Hack: Manually set cookies (for session support)
                req.prepare_cookies(self._session.cookies)

                self._response = self._session.send(req)
        except requests.exceptions.ConnectionError:
            raise check50.Failure('Server Connection failed.',
                help='Maybe the Server did not start')
        except requests.exceptions.InvalidSchema:
            raise check50.Failure('Invalid Url.',
                help='Maybe some redirects are faulty.')

    def _prefix_url(self, url):
        if urllib.parse.urlparse(url).netloc:
            return url

        if url.startswith('/'):
            return self._prefix + url
        else:
            return self._prefix + '/' + url

    def get(self, route, **kwargs):
        self._send('get', route, **kwargs)
        return self

    def post(self, route, **kwargs):
        self._send('post', route, **kwargs)
        return self

    def status(self, code, help=None):
        if (self._response.status_code != code):
            method = self._response.request.method;
            url = self._response.url[len(self._prefix):];
            if self._response.status_code == 404:
                help = f'Does a route for {method} {url} exist?'

            raise check50.Failure(f'expected status code {code} but got ' +
                f'{self._response.status_code} for {method} {url} ', help=help)
        return self

    def css_select(self, selectors, help=None):
        if not isinstance(selectors, list):
            selectors = [selectors]

        soup = BeautifulSoup(self._response.content)

        missing = []
        for s in selectors:
            if not soup.select_one(s):
                missing.append(s)

        if missing:
            raise check50.Failure('expect to find html elements matching ' +
                    ', '.join(missing), help=help)
        return self

    def content(self, regex, negate=False, help=None):
        if help is None:
            help = f'expected to find {regex}'

        check50.log(("checking that \"{}\" is in page").format(regex))

        text = BeautifulSoup(self._response.content).get_text(' ')

        regxp = re.compile(str(regex))
        found = regxp.search(text)
        if (negate and found) or (not negate and not found):
            raise check50.Failure(help)

        return self

    def register(self, username=None, password=None, confirmation=None):
        if username is None:
            username = self._username
        if password is None:
            password = self._password
        if confirmation is None:
            confirmation = self._password

        data = {
            'username': username,
            'password': password,
            'confirmation': confirmation,
        }
        self.post('/register', data=data)

        return self

    def login(self, username=None, password=None):
        if username is None:
            username = self._username
        if password is None:
            password = self._password

        data = {
            'username': username,
            'password': password,
        }
        self.post('/login', data=data)

        return self

    def quote(self, symbol):
        data = {
            'symbol': symbol,
        }
        self.post('/quote', data=data)
        return self

    def buy(self, symbol, count):
        data = {
            'symbol': symbol,
            'shares': count,
        }
        self.post('/buy', data=data)
        return self

    def sell(self, symbol, count):
        data = {
            'symbol': symbol,
            'shares': count,
        }
        self.post('/sell', data=data)
        return self
