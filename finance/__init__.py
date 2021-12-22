from dotenv import load_dotenv
import check50
import check50.py
import os
import requests

# Import express.py
check50.include('express.py')
express = check50.py.import_('./express.py')


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
    check50.run("npm install").exit(code=0, timeout=40)
    check50.exists("node_modules")


@check50.check(npm_install)
def startup():
    """application starts up"""
    with express.App() as app:
        app.get('/').status(200)


@check50.check(startup)
def register_page():
    """register page has all required elements"""
    with express.App() as app:
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
    with express.App() as app:
        for u in users:
            app.register(*u).status(400)


@check50.check(register_page)
def register_password_mismatch():
    """registration with password mismatch fails"""
    with express.App() as app:
        app.register("check50", "secret_123!", "secret_999!").status(400)


@check50.check(register_page)
def register():
    """registering user succeeds"""

    with express.App() as app:
        app.register().status(200)


@check50.check(register)
def register_duplicate_username():
    """registration rejects duplicate username"""
    with express.App() as app:
        app.register().status(400)


@check50.check(register)
def login_page():
    """login page has all required elements"""
    with express.App() as app:
        app.get('/login').status(200).css_select([
            'input[name=username]',
            'input[name=password]',
        ])


@check50.check(login_page)
def login_wrong_password():
    """login with wrong password fails"""
    with express.App() as app:
        app.login(password="wrong_password123").status(400)


@check50.check(login_page)
def login():
    """login as registered user succceeds"""
    with express.App() as app:
        app.login().status(200)


@check50.check(login)
def quote_page():
    """quote page has all required elements"""
    with express.App() as app:
        app.login().get('/quote').css_select('input[name=symbol]')


@check50.check(quote_page)
def quote_handles_invalid():
    """quote handles invalid ticker symbol"""
    with express.App() as app:
        app.login().quote("ZZZ").status(400)


@check50.check(quote_page)
def quote_handles_blank():
    """quote handles blank ticker symbol"""
    with express.App() as app:
        app.login().quote("").status(400)


@check50.check(quote_page)
def quote_handles_valid():
    """quote handles valid ticker symbol"""
    quote = quote_lookup('NFLX')

    with express.App() as app:
        (app.login()
           .quote('NFLX')
           .status(200)
           .content(quote['name'], help="Failed to find the quote's name.")
           .content(quote['price'], help="Failed to find the quote's price.")
           .content(quote['symbol'], help="Failed to find the quote's symbol."))


@check50.check(login)
def buy_page():
    """buy page has all required elements"""
    with express.App() as app:
        (app.login().get('/buy')
            .css_select(["input[name=shares]", "input[name=symbol]"]))


@check50.check(buy_page)
def buy_handles_invalid_ticker():
    """buy handles invalid ticker symbol"""
    with express.App() as app:
        app.login().buy("ZZZZ", 2).status(400)


@check50.check(buy_page)
def buy_handles_incorrect_shares():
    """buy handles fractional, negative, and non-numeric shares"""
    with express.App() as app:
        (app.login()
            .buy('TSLA', -1).status(400)
            .buy('TSLA', 1.5).status(400)
            .buy('TSLA', 'foo').status(400)
            .get('/')
            .content('Tesla', negate=True,
                help='Purchase succeded but it should not.'))

@check50.check(buy_page)
def buy_handles_out_of_balance():
    """buy handles out of balance situation"""
    with express.App() as app:
        (app.login()
            .buy('FB', 10000).status(400)
            .get('/')
            .content('Facebook', negate=True,
                help='Purchase succeded but it should not.'))



@check50.check(buy_page)
def buy_handles_valid():
    """buy handles valid purchase"""
    with express.App() as app:
        (app.login()
            .buy('NFLX', 10).status(200)
            .get('/')
            .content('NetFlix',
                help="Failed to find the bought quote's name on index page")
            .content('NFLX',
                help="Failed to find the bought quote's symbol on index page")
            .content(check50.regex.decimal(10),
                help="Failed to find the bought quote's count on index page"))


@check50.check(buy_handles_valid)
def sell_page():
    """sell page has all required elements"""
    with express.App() as app:
        (app.login().get('/sell')
            .css_select(['input[name=shares]', 'select[name=symbol]']))


@check50.check(buy_handles_valid)
def sell_handles_invalid():
    """sell handles invalid number of shares"""
    with express.App() as app:
        app.login().sell('NFLX', 999).status(400)


@check50.check(buy_handles_valid)
def sell_handles_valid():
    """sell handles valid sale"""
    with express.App() as app:
        (app.login()
            # A lot students forget to cast the form input to a Number.
            # String(2) > Number(10)
            # Take a number which first digit is lager than the first digit
            # of the users amount of shares.
            .sell('NFLX', 2)
            .status(200, help="Maybe you are comparing Strings with Numbers")
            .get('/')
            .content('NFLX',
                help="Failed to find the quote's symbol on index page")
            .content(check50.regex.decimal(10-2),
                help="Failed to find the quote's count on index page"))


def quote_lookup(symbol):
    load_dotenv(dotenv_path='.env')

    url = f'https://cloud.iexapis.com/stable/stock/{symbol}/quote'
    params = {
        'token': os.getenv('API_KEY'),
    }

    r = requests.get(url, params=params)

    if r.status_code != 200:
        raise check50.Failure('IEX Api did not respond with status code 200.' +
                f'Status code was {r.status_code}',
            help='Maybe you provided an invalid API key.')

    data = r.json()

    return {
        'name':   data['companyName'],
        'price':  data['latestPrice'],
        'symbol': data['symbol'],
    }
