from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User


class SignupForm(UserCreationForm):
    business = forms.CharField(max_length=120, label='Business name')
    username = forms.EmailField(label='Email address', max_length=150)

    class Meta:
        model = User
        fields = ('business','username','password1','password2')

    def clean_username(self):
        value = self.cleaned_data['username'].lower()
        if User.objects.filter(username__iexact=value).exists():
            raise forms.ValidationError('This email is already registered.')
        return value


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email address')

    def clean_username(self):
        return self.cleaned_data['username'].lower()
