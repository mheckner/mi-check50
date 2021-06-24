# mi-check50

check50 problems for MI @OTH.

## Why check50?
### Pro
- ability to alter checks **after** assignment start and without altering the
students repos
- uniform test environment (remote checking)
- cs50 as example course
- free and opensource

### Con
- unit testing javascript in python is cumbersome \
Solution: check50.flask.app like Wrapper class for nodejs express apps
- Students need to install another tool (no native Windows version)


## Technical
Please read [check50's guide](https://cs50.readthedocs.io/projects/check50/en/latest/).
Especially the section about [python checks](https://cs50.readthedocs.io/projects/check50/en/latest/check_writer/#getting-started-with-python-checks).

### Example
This is a basic check used for the finance app.
```js
@check50.check(npm_install)
def startup():
    """application starts up"""
    with express.App() as app:
        app.get('/').status(200)
```
The basic components are:
- **Decorator** `@check50.check()` \
It marks the function `startup` as check.
- **Dependency** (optional) `npm_install` \
The check `startup` will only run if the check `npm_install` has passed.
- **Instance of App** \
The [App class](#app_class) capsules a nodejs instance of the finance app.
- **Requests** `app.get()` or `app.post()` \
Sends a GET/POST request to the finance app.
- **Conditions** `app.status(200)` or `app.css_select()`
Perform checks on the last response from the finance app.
E.g. Does the http status code match?
Does the returned html document contain certain elements?

### <a name="app_class"></a> App Class
A check50.flask.app like wrapper class for nodejs express apps.
It provides methods to send GET or POST requests to the students app and
methods to validate the app's response.
It also contains special functionality for the finance app (`login`, `buy`,`sell`).
This could be put in a subclass (see [TODO](#todo)).

Request injection into the express router system is not possible.
So we simply start the student's app as subprocess (`node app.js`).

> Checks are run in parallel by check50. Each check is run in worker process.
Synchronisation via global variables does not work therefore.
As the checks might fail at any stage. We do not know which check is the last one
running.

To ensure the subprocess is terminated after all checks have run or a check failed,
we start a new node instance for each check.
For proper cleanup the App Class supports the Python with-statement
([Explanation on python resource statement](https://stackoverflow.com/a/1369553).

To support parallel testing the student's app instances have to listen to different
ports to prevent port collision. The easiest way is to use unix domain socket.
They are local to each checks filesystem.


### TODO
- Extract finance functionality from App Class. \
  Goal: Resuable Library for other node-express-based assignments.
    
- Fix import other python files in `__init__.py`.
  Current implementation is not bullet proof.
  
- Remove manuell redirection code as much as possible.

- Add docstrings for methods. In other words, more code comments.

- Repl.it template with check50 preinstalled.


### Further Resources
- [check50 doc](https://cs50.readthedocs.io/projects/check50/en/latest/)
- [example checks](https://github.com/cs50/problems)
- [check50 source](https://github.com/cs50/check50)
