from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp
from ..models import User


class RegisterForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(2, 100)])
    phone = StringField('Phone', validators=[
        DataRequired(),
        Length(min=10, max=12),
        Regexp(r'^\d+$', message='Phone must contain digits only.')
    ])
    password = PasswordField('Password', validators=[DataRequired(), Length(6, 100)])
    confirm = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match.')
    ])
    submit = SubmitField('Register')

    def validate_phone(self, field):
        if User.query.filter_by(phone=field.data.strip()).first():
            raise ValidationError('Phone number already registered.')


class LoginForm(FlaskForm):
    phone = StringField('Phone', validators=[
        DataRequired(),
        Length(min=10, max=12)
    ])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')