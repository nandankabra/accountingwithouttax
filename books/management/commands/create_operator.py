import getpass
import os
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


class Command(BaseCommand):
    help='Create a product administrator. Password is prompted or read from OPERATOR_PASSWORD.'
    def add_arguments(self,parser):parser.add_argument('--email',required=True)
    def handle(self,*args,**options):
        email=options['email'].lower()
        try:validate_email(email)
        except ValidationError:raise CommandError('Enter a valid login email address.')
        if len(email)>150:raise CommandError('Login email must be at most 150 characters.')
        if User.objects.filter(username__iexact=email).exists():raise CommandError('This login already exists; existing permissions were not changed.')
        password=os.environ.get('OPERATOR_PASSWORD') or getpass.getpass('Choose product administrator password: ')
        user=User(username=email,email=email,is_staff=True,is_superuser=True)
        try:validate_password(password,user)
        except ValidationError as error:raise CommandError(' '.join(error.messages))
        user.set_password(password);user.save()
        self.stdout.write(f'Created product administrator {email}. Sign in at /admin/.')
