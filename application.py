import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

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

    # Save user's id and username
    user_id = session["user_id"]
    username = session["username"]

    # Get user's account balance from table users
    user = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)
    balance = float(user[0]["cash"])

    stocks_value = 0
    profit = 0

    # Get user's stock portfolio
    stocks = db.execute("SELECT * FROM :user_account ORDER BY symbol ASC", user_account=username)

    # List every stock position
    for i in range(len(stocks)):
        stock = lookup(stocks[i]["symbol"])
        stocks[i]["company"] = stock["name"]
        stocks[i]["unit_value"] = float(stock["price"])
        stocks[i]["total_value"] = float(stock["price"]) * float(stocks[i]["shares"])

        stocks_value += float(stock["price"]) * float(stocks[i]["shares"])

    total_assets = balance + stocks_value

    # Render index.html with stock and funds summary
    return render_template("index.html", balance=balance, stocks=stocks, total_assets=total_assets, stocks_value=stocks_value)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # COLLECTING AND CHECKING DATA FROM SUBMITTED FORM
        # Ensure stock symbol was submitted
        if not request.form.get("symbol"):
            return render_template("buy.html")

        # Ensure number of shares was submited
        if not request.form.get("shares"):
            return render_template("buy.html")

        # Ensure input in field 'shares' is integer
        if not request.form.get("shares").isdigit():
            return render_template("buy.html")

        # Ensure number of shares is greater than 0
        if int(request.form.get("shares")) <= 0:
            return render_template("buy.html")

        # Request for stock information using submitted stock symbol
        stock = lookup(request.form.get("symbol"))

        # If submitted symbol does not mach any stock symbol from data provider
        if not stock:
            return apology("symbol not found or wrong symbol", 403)


        # TRANSACTION PROCESS
        # Save transaction type
        transaction_type = "buy"
        # Save user id
        user_id = session["user_id"]
        # Save stock symbol
        symbol = request.form.get("symbol")
        # Save amount of shares
        amount = int(request.form.get("shares"))
        # Extract price of single share
        price = float(stock["price"])


        # Calculate total cost of potential purchase
        total_price = price * float(amount)

        # Get user's account balance
        user = db.execute("SELECT * FROM users WHERE id = :id", id=user_id)
        balance = float(user[0]["cash"])

        # Compare account balance with total price of purchase
        # If total price is greater than balance, comunicate an error
        if balance < total_price:
            return apology("not enough credit", 403)

        # Calculate new account balance
        updated_balance = balance - total_price

        # Update balance in database, table 'users'
        db.execute("UPDATE users SET cash = :updated_balance WHERE id = :id", updated_balance=updated_balance, id=user_id)

        # Register transaction in history
        db.execute("INSERT INTO history (username, type, symbol, shares, total_value, balance_before, balance_after) VALUES (:username, :type, :symbol, :shares, :total_value, :balance_before, :balance_after)", username=session["username"], type=transaction_type, symbol=symbol, shares=amount, total_value=(amount * price), balance_before=balance, balance_after=balance-(amount * price))

        # Check in database if any other stocks with matching symbol were found
        matching_stocks = db.execute("SELECT * FROM :user_account WHERE symbol = :symbol", user_account=session["username"], symbol=symbol)
        if len(matching_stocks) != 0:
            existing_amount = matching_stocks[0]["shares"]
            existing_symbol = matching_stocks[0]["symbol"]
            # If matching stocks found, update number of shares
            db.execute("UPDATE :user_account SET shares = :shares_amount WHERE symbol = :symbol", user_account=session["username"], shares_amount=existing_amount+amount, symbol=existing_symbol)

        # If no stocks with matching symbol were found
        else:
            # Save bought stocks in database, table ':username', where username=session["username"]
            db.execute("INSERT INTO :user_account (symbol, shares) VALUES (:stock_symbol, :shares_amount)", user_account=session["username"], stock_symbol=symbol, shares_amount=amount)

        # After succesful transaction redirect to main page with account summary
        return index()

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():

    # Save user's id and username
    user_id = session["user_id"]
    username = session["username"]

    # Get user's history from database
    history = db.execute("SELECT * FROM history WHERE username = :username", username = username)

    # Render history.html with user's records
    return render_template("history.html", history=history)



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
        session["user_id"] = rows[0]["id"]
        session["username"] = rows[0]["username"]

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

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure stock symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing stock symbol", 403)

        # Request for stock information using submitted stock symbol
        stock = lookup(request.form.get("symbol"))

        # If submitted symbol does not mach any stock symbol from data provider
        if not stock:
            return apology("symbol not found or wrong symbol", 403)

        # If stock data was collected, render quoted.html with gained data
        return render_template("quoted.html", symbol=stock["symbol"], name=stock["name"], price=stock["price"])

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    # This method registers new user by adding to database's table 'users'
    # it also creates new table to store user's transactions

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("missing username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("missing password", 403)

        # Ensure typed password and confirmation are equal
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords are not equal", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Check if username already exists
        if len(rows) != 0:
            return apology("user already exists, choose different username", 403)

        # Query database for table to get number of users
        rows = db.execute("SELECT id FROM users")

        # Save username from posted form
        new_username = request.form.get("username")

        # Generate password hash
        new_hash = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)

        # Add new user to database, table 'users'
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=new_username, hash=new_hash)

        # Create new table with name equal to user's username to create user's stock portfolio
        db.execute("CREATE TABLE :username(symbol TEXT, shares INTEGER)", username=new_username)

        # Redirect user to login page
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # COLLECTING AND CHECKING DATA FROM SUBMITTED FORM
        # Ensure stock symbol was submitted
        if not request.form.get("symbol"):
            return render_template("sell.html")

        # Ensure number of shares was submited
        if not request.form.get("shares"):
            return render_template("sell.html")

        # Ensure input in field 'shares' is integer
        if not request.form.get("shares").isdigit():
            return render_template("sell.html")

        # Ensure number of shares is greater than 0
        if int(request.form.get("shares")) <= 0:
            return render_template("sell.html")

        # Request for stock information using submitted stock symbol
        stock = lookup(request.form.get("symbol"))

        # If submitted symbol does not mach any stock symbol from data provider
        if not stock:
            return apology("symbol not found or wrong symbol", 403)


        # TRANSACTION PROCESS
        # Save transaction type
        transaction_type = "sell"
        # Save user id
        user_id = session["user_id"]
        # Save stock symbol
        symbol = request.form.get("symbol")
        # Save amount of shares
        amount = int(request.form.get("shares"))
        # Extract price of single share
        price = float(stock["price"])
        # Calculate total value of potential sale
        total_price = price * float(amount)

        # Check if there are stocks with matching symbol in user's account
        matching_stocks = db.execute("SELECT * FROM :user_account WHERE symbol = :symbol", user_account=session["username"], symbol=symbol)
        if len(matching_stocks) == 0:
            return apology("You dont have requested stocks in your account")


        # SALE
        # Check if there are enough shares to finalize sale
        elif matching_stocks[0]["shares"] < amount:
            return apology("You dont have enough shares of pointed stock")

        # If user wants to sell all shares of particular stock
        elif matching_stocks[0]["shares"] == amount:
            db.execute("DELETE FROM :user_account WHERE symbol = :symbol", user_account=session["username"], symbol=symbol)

        elif matching_stocks[0]["shares"] > amount:
            db.execute("UPDATE :user_account SET shares = :shares WHERE symbol = :symbol", user_account=session["username"], shares=matching_stocks[0]["shares"]-amount, symbol=symbol)

        #UPDATE FUNDS
        # Get user's account balance
        user = db.execute("SELECT * FROM users WHERE id = :id", id=user_id)
        balance = float(user[0]["cash"])

        # Calculate new account balance
        updated_balance = balance + total_price

        # Update balance in database, table 'users'
        db.execute("UPDATE users SET cash = :updated_balance WHERE id = :id", updated_balance=updated_balance, id=user_id)

        # Register transaction in history
        db.execute("INSERT INTO history (username, type, symbol, shares, total_value, balance_before, balance_after) VALUES (:username, :type, :symbol, :shares, :total_value, :balance_before, :balance_after)", username=session["username"], type=transaction_type, symbol=symbol, shares=amount, total_value=(amount * price), balance_before=balance, balance_after=updated_balance)

        # After succesful transaction redirect to main page with account summary
        return index()

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
