import os
import requests
import pytz


from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    rows= db.execute("SELECT * FROM stock")
    return render_template ("index.html", rows=rows)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol= request.form.get("symbol")
        symbol=symbol.upper()
        samesymbol_price=db.execute("SELECT total FROM stock WHERE symbol = :symbol",symbol=symbol)
        share= float(request.form.get("share"))
        key = os.environ.get("API_KEY")
        resp = requests.get(f'https://cloud-sse.iexapis.com/stable/stock/{symbol}/quote?token={key}')
        if len(samesymbol_price)>0:
            prevshare = db.execute("SELECT share FROM stock WHERE symbol = :symbol", symbol=symbol)[0]['share']
            prevshare= float(prevshare)
            newshare= share+prevshare
            price= float(resp.json()['latestPrice'])
            newtotal=price*newshare
            newtotal=f'${newtotal}'
            tz_IN = pytz.timezone('Asia/Kolkata')
            datetime_IN = datetime.now(tz_IN)
            transacted = datetime_IN.strftime("%d-%m-%Y %H:%M:%S")
            cash=db.execute("SELECT total FROM stock WHERE symbol = 'CASH'")[0]['total']
            cash=float(cash[1:len(cash)])
            if (share*price)<=cash:
                newcash=cash-(share*price)
                newcash= f'${newcash}'
                db.execute('''
                        UPDATE stock
                        SET total=%s
                        WHERE symbol = 'CASH'
                        ''',newcash)
                price= f'${price}'
                db.execute('''
                        UPDATE stock
                        SET share=%s,total=%s
                        WHERE symbol = %s
                         ''',newshare,newtotal,symbol)
                db.execute("INSERT INTO history (symbol, share, price, transacted) VALUES (:symbol, :share, :price, :transacted)", symbol=symbol, share=share, price=price, transacted=transacted)
                flash('Bought!')
                return redirect("/")
            else:
                flash("Not enough cash!")
                return render_template("buy.html")

        if resp.status_code == 200:
            price= float(resp.json()['latestPrice'])
            name = resp.json()['companyName']
            total= price*share
            cash=db.execute("SELECT total FROM stock WHERE symbol = 'CASH'")[0]['total']
            cash=float(cash[1:len(cash)])
            if total<=cash:
                newcash=cash-total
                newcash= f'${newcash}'
                db.execute('''
                        UPDATE stock
                        SET total=%s
                        WHERE symbol = 'CASH'
                        ''',newcash)
                total= f'${total}'
                price= f'${price}'
                tz_IN = pytz.timezone('Asia/Kolkata')
                datetime_IN = datetime.now(tz_IN)
                transacted = datetime_IN.strftime("%d-%m-%Y %H:%M:%S")
                db.execute("INSERT INTO stock (symbol, name, share, price, total) VALUES (:symbol, :name, :share, :price, :total)", symbol=symbol, name=name, share=share, price=price, total=total)
                db.execute("INSERT INTO history (symbol, share, price, transacted) VALUES (:symbol, :share, :price, :transacted)", symbol=symbol, share=share, price=price, transacted=transacted)
                flash('Bought!')
                return redirect("/")
            else:
                flash("Not enough cash!")
                return render_template("buy.html")
        else:
            flash('Invalid symbol!')
            return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    rows= db.execute("SELECT * FROM history")
    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user"] = rows[0]["username"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        symbol=symbol.upper()
        key = os.environ.get("API_KEY")
        resp = requests.get(f'https://cloud-sse.iexapis.com/stable/stock/{symbol}/quote?token={key}')
        if resp.status_code == 200:
            company = resp.json()['companyName']
            price= resp.json()['latestPrice']
            return render_template("quoted.html", company=company, price=price, symbol=symbol)
        else:
            flash('Invalid symbol!')
            return render_template("quote.html")




@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        hash = request.form.get("hash1")
        conhash = request.form.get("hash2")
        if hash == conhash:
            hash = generate_password_hash(hash)
            try:
                db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)
                return redirect("/")
            except RuntimeError:
                flash('Username already exist!')
                return render_template('register.html')
        else:
            flash('Passwords does not match!')
            return render_template('register.html')



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        rows= db.execute("SELECT * FROM stock")
        return render_template("sell.html", rows=rows)
    else:
        curshare = int(request.form.get("share"))
        symbol = request.form.get("symbol")
        key = os.environ.get("API_KEY")
        resp = requests.get(f'https://cloud-sse.iexapis.com/stable/stock/{symbol}/quote?token={key}')
        price= resp.json()['latestPrice']
        prevshare = db.execute("SELECT share FROM stock WHERE symbol = :symbol", symbol=symbol)[0]['share']
        if curshare<=prevshare:
            share=prevshare-curshare
            cashtotal=price*curshare
            total=price*share
            cash=db.execute("SELECT total FROM stock WHERE symbol = 'CASH'")[0]['total']
            cash=float(cash[1:len(cash)])
            newcash=cash+cashtotal
            newcash= f'${newcash}'
            db.execute('''
                    UPDATE stock
                    SET total=%s
                    WHERE symbol = 'CASH'
                    ''',newcash)
            total=f'${total}'
            price=f'${price}'
            tz_IN = pytz.timezone('Asia/Kolkata')
            datetime_IN = datetime.now(tz_IN)
            transacted = datetime_IN.strftime("%d-%m-%Y %H:%M:%S")
            db.execute("INSERT INTO history (symbol, share, price, transacted) VALUES (:symbol, :share, :price, :transacted)", symbol=symbol, share=-curshare, price=price, transacted=transacted)
            flash('Sold!')
            if share==0:
                db.execute("DELETE FROM stock WHERE symbol=:symbol", symbol=symbol)
                return redirect("/")
            else:
                db.execute('''
                        UPDATE stock
                        SET share = %s ,price = %s,total=%s
                        WHERE symbol = %s
                        ''',share,price,total,symbol)
                return redirect("/")
        else:
            flash('Not enough shares to sell!')
            return render_template('sell.html')



def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
