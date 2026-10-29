from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp
from ..models import User
from ..utils import normalize_phone


class RegisterForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(2, 100)])
    phone = StringField('Phone', validators=[DataRequired(), Length(min=10, max=16)])
    password = PasswordField('Password', validators=[DataRequired(), Length(8, 100)])
    confirm = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match.')
    ])
    marketing = BooleanField('Send me offers by SMS (optional, you can opt out any time)')
    submit = SubmitField('Register')

    def validate_phone(self, field):
        phone = normalize_phone(field.data)
        if not phone:
            raise ValidationError('Enter a valid mobile number, e.g. 09123456789.')
        existing = User.query.filter_by(phone=phone).first()
        if existing and existing.phone_verified:
            raise ValidationError('Phone number already registered.')
        field.data = phone


class LoginForm(FlaskForm):
    phone = StringField('Phone', validators=[DataRequired(), Length(min=10, max=16)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class CodeForm(FlaskForm):
    code = StringField('Verification code', validators=[DataRequired(), Length(6, 6), Regexp(r'^\d{6}$', message='Enter the 6-digit code.')])
    submit = SubmitField('Verify')


class ForgotForm(FlaskForm):
    phone = StringField('Phone', validators=[DataRequired(), Length(min=10, max=16)])
    submit = SubmitField('Send code')


class ResetForm(FlaskForm):
    code = StringField('Code', validators=[DataRequired(), Length(6, 6), Regexp(r'^\d{6}$', message='Enter the 6-digit code.')])
    password = PasswordField('New password', validators=[DataRequired(), Length(8, 100)])
    confirm = PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit = SubmitField('Reset password')
