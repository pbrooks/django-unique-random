# -*- coding: utf-8 -*-
import hashlib
import os
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_backends
from django.core.urlresolvers import reverse_lazy
from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.contrib.sites.shortcuts import get_current_site

from .utils import AUTH_USER_MODEL, get_username


class LoginCode(models.Model):
    user = models.ForeignKey(AUTH_USER_MODEL, related_name='login_codes',
                             editable=False, verbose_name=_('user'))
    code = models.CharField(max_length=20, editable=False, verbose_name=_('code'), unique=True)
    timestamp = models.DateTimeField(editable=False)
    next = models.TextField(editable=False, blank=True)

    def __unicode__(self):
        return "%s - %s" % (self.user, self.timestamp)

    def save(self, *args, **kwargs):
        if settings.USE_TZ:
            self.timestamp = timezone.now()
        else:
            self.timestamp = datetime.now()

        if not self.next:
            self.next = '/'
        super(LoginCode, self).save(*args, **kwargs)

    def login_url(self, secure=False, host=None):
        username = get_username(self.user)
        site = get_current_site(None)
        if site:
            host = site.domain
        else:
            host = getattr(settings, 'SERVER_URL', None) or 'example.com'
        if getattr(settings, 'NOPASSWORD_HIDE_USERNAME', False):
            view = reverse_lazy('nopassword.views.login_with_code', kwargs={'login_code': self.code}),
        else:
            view = reverse_lazy('nopassword.views.login_with_code_and_username',
                                kwargs={'username': username, 'login_code': self.code}),

        return '%s://%s%s?next=%s' % (
            'https' if secure else 'http',
            host,
            view[0],
            self.next
        )

    def send_login_code(self, secure=False, host=None, **kwargs):
        for backend in get_backends():
            if hasattr(backend, 'send_login_code'):
                backend.send_login_code(self, secure=secure, host=host, **kwargs)

    @classmethod
    def create_code_for_user(cls, user, next=None):
        if not user.is_active:
            return None

        code = None
        while not cls.code_is_valid(code):
            code = cls.generate_code(length=getattr(settings, 'NOPASSWORD_CODE_LENGTH', 20))
        login_code = LoginCode(user=user, code=code)
        if next is not None:
            login_code.next = next
        login_code.save()
        return login_code

    @classmethod
    def generate_code(cls, length=20):
        hash_algorithm = getattr(settings, 'NOPASSWORD_HASH_ALGORITHM', 'sha256')
        m = getattr(hashlib, hash_algorithm)()
        m.update(getattr(settings, 'SECRET_KEY', None).encode('utf-8'))
        m.update(os.urandom(16))
        if getattr(settings, 'NOPASSWORD_NUMERIC_CODES', False):
            hashed = str(int(m.hexdigest(), 16))[-length:]
        else:
            hashed = m.hexdigest()[:length]
        return hashed

    @classmethod
    def code_is_valid(cls, code):
        if not code:
            return False
        return LoginCode.objects.filter(code=code).exists()
