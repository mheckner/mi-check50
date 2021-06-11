from bs4 import BeautifulSoup
from dotenv import load_dotenv
from random import randint
import os
import re
import requests
import requests_unixsocket
import subprocess
import time
import urllib.parse

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


@check50.check(register_page)
def register():
    """registering user succeeds"""

    with App() as app:
        app.register().status(200)


@check50.check(register)
def register_duplicate_username():
    """registration rejects duplicate username"""
    with App() as app:
        app.register().status(400)


@check50.check(startup)
def login_page():
    """login page has all required elements"""
    with App() as app:
        app.get('/login').status(200).css_select([
            'input[name=username]',
            'input[name=password]',
        ])


@check50.check(register)
def login():
    """login as registered user succceeds"""
    with App() as app:
        app.login().status(200).get("/", allow_redirects=False).status(200)


@check50.check(login)
def quote_page():
    """quote page has all required elements"""
    with App() as app:
        app.login().get('/quote').css_select('input[name=symbol]')


@check50.check(quote_page)
def quote_handles_invalid():
    """quote handles invalid ticker symbol"""
    with App() as app:
        app.login().quote("ZZZ").status(400)


@check50.check(quote_page)
def quote_handles_blank():
    """quote handles blank ticker symbol"""
    with App() as app:
        app.login().quote("").status(400)


@check50.check(quote_page)
def quote_handles_valid():
    """quote handles valid ticker symbol"""
    quote = quote_lookup('NFLX')

    with App() as app:
        (app.login()
           .quote('NFLX')
           .status(200)
           .content(quote['name'], help="Failed to find the quote's name.")
           .content(quote['price'], help="Failed to find the quote's price.")
           .content(quote['symbol'], help="Failed to find the quote's symbol."))


@check50.check(login)
def buy_page():
    """buy page has all required elements"""
    with App() as app:
        (app.login().get('/buy')
            .css_select(["input[name=shares]", "input[name=symbol]"]))


@check50.check(buy_page)
def buy_handles_invalid_ticker():
    """buy handles invalid ticker symbol"""
    with App() as app:
        app.login().buy("ZZZZ", 2).status(400)


@check50.check(buy_page)
def buy_handles_incorrect_shares():
    """buy handles fractional, negative, and non-numeric shares"""
    with App() as app:
        (app.login()
            .buy('NFLX', -1).status(400)
            .buy('NFLX', 1.5).status(400)
            .buy('NFLX', 'foo').status(400))

@check50.check(buy_page)
def buy_handles_out_of_balance():
    """buy handles out of balance situation"""
    with App() as app:
        app.login().buy('NFLX', 10000).status(400)


@check50.check(buy_page)
def buy_handles_valid():
    """buy handles valid purchase"""
    with App() as app:
        (app.login()
            .buy('NFLX', 4).status(200)
            .get('/')
            .content('NFLX',
                help="Failed to find the bought quote's symbol on index page")
            .content(check50.regex.decimal(4),
                help="Failed to find the bought quote's count on index page"))


@check50.check(buy_handles_valid)
def sell_page():
    """sell page has all required elements"""
    with App() as app:
        (app.login().get('/sell')
            .css_select(['input[name=shares]', 'select[name=symbol]']))


@check50.check(buy_handles_valid)
def sell_handles_invalid():
    """sell handles invalid number of shares"""
    with App() as app:
        app.login().sell('NFLX', 8).status(400)


@check50.check(buy_handles_valid)
def sell_handles_valid():
    """sell handles valid sale"""
    with App() as app:
        (app.login()
            .sell('NFLX', 2)
            .status(200)
            .get('/')
            .content('NFLX',
                help="Failed to find the quote's symbol on index page")
            .content(check50.regex.decimal(2),
                help="Failed to find the quote's count on index page"))


def quote_lookup(symbol):
    load_dotenv(dotenv_path='.env')

    url = f'https://cloud.iexapis.com/stable/stock/{symbol}/quote'
    params = {
        'token': os.getenv('API_KEY'),
    }

    r = requests.get(url, params=params)
    data = r.json()

    return {
        'name':   data['companyName'],
        'price':  data['latestPrice'],
        'symbol': data['symbol'],
    }


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
        follow_redirects = kwargs.get('allow_redirects', True)
        kwargs.setdefault('allow_redirects', False)

        try:
            self._response = self._session.request(method=method, url=url,
                **kwargs)

            if not follow_redirects:
                return

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

    def status(self, code):
        if (self._response.status_code != code):
            method = self._response.request.method;
            url = self._response.url[len(self._prefix):];
            help = None
            if self._response.status_code == 404:
                help = f'Does a route for {method} {url} exist?'

            raise check50.Failure(f'expected status code {code} but got ' +
                f'{self._response.status_code} for {method} {url} ', help=help)
        return self

    def css_select(self, selectors):
        if not isinstance(selectors, list):
            selectors = [selectors]

        soup = BeautifulSoup(self._response.content)

        missing = []
        for s in selectors:
            if not soup.select_one(s):
                missing.append(s)

        if missing:
            raise check50.Failure('expect to find html elements matching ' +
                    ', '.join(missing))
        return self

    def content(self, regex, help=None):
        if help is None:
            help = f'expected to find {regex}'

        text = BeautifulSoup(self._response.content).get_text(' ')

        regxp = re.compile(str(regex))
        if not regxp.search(text):
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
