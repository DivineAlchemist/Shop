import logging
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from .forms import RegisterForm, LoginForm, CodeForm, ForgotForm, ResetForm
from ..models import User
from ..extensions import db
from ..i18n import flash  # translated flash messages
from ..utils import normalize_phone, safe_next_url
from ..services import verification
from ..services.notifications import set_marketing_consent

auth_bp = Blueprint('auth', __name__)
log = logging.getLogger(__name__)


def _verification_required():
    return current_app.config.get('SMS_VERIFICATION_REQUIRED', True)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('customer.index'))
    form = RegisterForm()
    if form.validate_on_submit():
        phone = form.phone.data
        user = User.query.filter_by(phone=phone).first()  # only unverified accounts can reach here
        if user is None:
            user = User(phone=phone, role='customer')
            db.session.add(user)
        user.name = form.name.data
        user.set_password(form.password.data)
        user.phone_verified = not _verification_required()
        db.session.commit()
        if form.marketing.data:
            set_marketing_consent(user, True)
        if not _verification_required():
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        ok, err = verification.issue_code(phone, 'register', user.id)
        session['verify_phone'] = phone
        flash('We sent a verification code by SMS.' if ok else err, 'success' if ok else 'warning')
        return redirect(url_for('auth.verify'))
    return render_template('auth/register.html', form=form)


@auth_bp.route('/verify', methods=['GET', 'POST'])
def verify():
    phone = session.get('verify_phone')
    if not phone:
        return redirect(url_for('auth.register'))
    form = CodeForm()
    if form.validate_on_submit():
        ok, err = verification.check_code(phone, 'register', form.code.data)
        if ok:
            user = User.query.filter_by(phone=phone).first()
            if user:
                user.phone_verified = True
                db.session.commit()
            session.pop('verify_phone', None)
            flash('Phone verified. Please log in.', 'success')
            return redirect(url_for('auth.login'))
        flash(err, 'danger')
    return render_template('auth/verify.html', form=form, phone=phone)


@auth_bp.route('/verify/resend', methods=['POST'])
def verify_resend():
    phone = session.get('verify_phone')
    if not phone:
        return redirect(url_for('auth.register'))
    ok, err = verification.issue_code(phone, 'register')
    flash('A new code was sent.' if ok else err, 'success' if ok else 'warning')
    return redirect(url_for('auth.verify'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('customer.index'))
    form = LoginForm()
    if form.validate_on_submit():
        phone = normalize_phone(form.phone.data) or form.phone.data.strip()
        user = User.query.filter_by(phone=phone).first()
        cfg = current_app.config
        if user and user.is_locked():
            flash('Too many failed attempts. Try again later or reset your password.', 'danger')
        elif user and user.is_active_account and user.check_password(form.password.data):
            if not user.phone_verified:
                session['verify_phone'] = user.phone
                verification.issue_code(user.phone, 'register', user.id)
                flash('Please verify your phone number first.', 'warning')
                return redirect(url_for('auth.verify'))
            user.failed_logins, user.locked_until = 0, None
            db.session.commit()
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(safe_next_url(request.args.get('next')) or url_for('customer.index'))
        else:
            if user:
                user.failed_logins += 1
                if user.failed_logins >= cfg['LOGIN_MAX_FAILURES']:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=cfg['LOGIN_LOCK_MINUTES'])
                    user.failed_logins = 0
                db.session.commit()
            flash('Invalid phone number or password.', 'danger')
    return render_template('auth/login.html', form=form)


@auth_bp.route('/forgot', methods=['GET', 'POST'])
def forgot():
    form = ForgotForm()
    if form.validate_on_submit():
        phone = normalize_phone(form.phone.data)
        user = User.query.filter_by(phone=phone).first() if phone else None
        if user and user.phone_verified:
            verification.issue_code(phone, 'reset', user.id)
        session['reset_phone'] = phone or form.phone.data.strip()
        # identical response whether or not the account exists (no user enumeration)
        flash('If that number has an account, a recovery code was sent by SMS.', 'info')
        return redirect(url_for('auth.reset'))
    return render_template('auth/forgot.html', form=form)


@auth_bp.route('/reset', methods=['GET', 'POST'])
def reset():
    phone = session.get('reset_phone')
    if not phone:
        return redirect(url_for('auth.forgot'))
    form = ResetForm()
    if form.validate_on_submit():
        ok, err = verification.check_code(phone, 'reset', form.code.data)
        user = User.query.filter_by(phone=phone).first()
        if ok and user:
            user.set_password(form.password.data)
            user.failed_logins, user.locked_until = 0, None
            db.session.commit()
            session.pop('reset_phone', None)
            flash('Password updated. Please log in.', 'success')
            return redirect(url_for('auth.login'))
        flash(err or 'The code is invalid or has expired.', 'danger')
    return render_template('auth/reset.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('customer.index'))
