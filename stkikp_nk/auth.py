import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from NLPCBR.db import get_db

bp = Blueprint('auth', __name__)

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        
        return view(**kwargs)
    
    return wrapped_view

def logout_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user:
            return redirect(url_for('main.input'))
        
        return view(**kwargs)
    
    return wrapped_view

@bp.route('/register', methods=('GET', 'POST'))
@logout_required
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        fullname = request.form['fullname']
        nickname = request.form['nickname']
        db = get_db()
        errors = []

        if not email:
            errors += ['Email is required']
        elif not password:
            errors += ['Password is required']
        elif not fullname:
            errors += ['Fullname is required']
        elif not nickname:
            errors += ['Nickname is required']
        
        if not len(errors):
            try:
                db.execute(
                    "INSERT INTO users (email, password, fullname, nickname) VALUES (?, ?, ?, ?)",
                    (email, generate_password_hash(password), fullname, nickname),
                )
                db.commit()
            except db.IntegrityError:
                errors += [f"{email} is already registered."]
            else:
                return redirect(url_for("auth.login"))
        
        if len(errors):
            for error in errors:
                flash(error)
    
    return render_template('auth/register.html')

@bp.route('/login', methods=('GET', 'POST'))
@logout_required
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        errors = []
        user = db.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()

        if not user:
            errors += ['Incorrect email']
        elif not check_password_hash(user['password'], password):
            errors += ['Incorrect password']

        if not len(errors):
            session.clear()
            session['user_id'] = user['user_id']
            return redirect(url_for('main.input'))
        else:
            for error in errors:
                flash(error)
    
    return render_template('auth/login.html')

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        ).fetchone()

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.input'))

@bp.route('/edit_account', methods=('GET', 'POST'))
@login_required
def edit_account():
    db = get_db()
    user_id = session.get('user_id')
    user = db.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
            ).fetchone()
    
    if request.method == 'POST':
        email = request.form['email']
        fullname = request.form['fullname']
        nickname = request.form['nickname']
        new_password = request.form['new_password']
        db = get_db()
        errors = []

        if not email:
            errors += ['Email is required']
        elif not fullname:
            errors += ['Fullname is required']
        elif not nickname:
            errors += ['Nickname is required']
        elif not check_password_hash(user['password'], request.form['old_password']):
            errors += ['Incorrect password']
        
        if not len(errors):
            try:
                if not new_password:
                    db.execute(
                        """UPDATE users 
                        SET email = ?, fullname = ?, nickname = ?
                        WHERE user_id = ?""",
                        (email, fullname, nickname, user_id),
                    )
                    db.commit()
                elif new_password:
                    db.execute(
                        """UPDATE users 
                        SET email = ?, fullname = ?, nickname = ?, password = ?
                        WHERE user_id = ?""",
                        (email, fullname, nickname, generate_password_hash(new_password), user_id),
                    )
                    db.commit()
            except db.IntegrityError:
                errors += [f"{email} is already registered."]
            else:
                return redirect(url_for("auth.edit_account"))
        
        if len(errors):
            for error in errors:
                flash(error)

    return render_template('auth/edit_account.html', email=user['email'], fullname=user['fullname'], nickname=user['nickname'])

@bp.route('/delete_account')
@login_required
def delete_account():
    db = get_db()
    user_id = session.get('user_id')
    db.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    db.commit()

    return redirect(url_for("auth.logout"))